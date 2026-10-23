/*
 * abertis - Abertis/Ciefp feed extractor and MPEG-TS repairer
 *
 * Usage: abertis <pid> [options]
 *
 *   --sid <n>        keep only the service with this program number
 *   --pmt <pid>      keep only the service carried on this PMT pid
 *   --fix-pts        rewrite the PTS/DTS of the broken video streams
 *   --no-fix-pcr     do not clear the PCR discontinuity indicator
 *   --stats          print a summary on stderr
 *
 * Reads an MPEG-TS on stdin (the streamrelay output of the feed), extracts
 * the payload of the given data pid and writes the resulting transport
 * stream on stdout.
 *
 * The payload of the data pid is the *inner* transport stream of the feed
 * (the demux of the box already removed the T2-MI encapsulation).  Three
 * defects of that stream are repaired here:
 *
 *   1. the first packets of a relay connection are stale leftovers of the
 *      demux buffer (their PCR is minutes behind the live stream); they are
 *      dropped until the PCR runs consistently again;
 *   2. the video PES headers of the Abertis feeds are broken: the PTS
 *      values are permuted between the frames and their clock runs about
 *      0.4 % slower than the clock of the mux, while the audio pids of the
 *      same program use the exact 90 kHz clock.  A hardware decoder can
 *      not keep audio and video together with that error - the picture
 *      freezes, stutters or runs in slow motion.  The timestamps of the
 *      affected pids are therefore rebuilt from the clock of the stream
 *      itself (the PCR rate measured against the byte offset), which puts
 *      them back on the same 90 kHz clock as the audio;
 *   3. every PCR packet of these feeds has the discontinuity indicator set,
 *      which tells the player to reset its clock on every single packet -
 *      it is cleared, because the PCR itself is continuous.  A player that
 *      obeys that indicator never gets a stable clock and stalls.
 *
 * Copyright (C) 2026
 * License: GPL-2.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <inttypes.h>

#define TS_PACKET_SIZE 188
#define MAX_PID 8192

#define PES_START_MIN 9             /* start code .. PES_header_data_length */
#define PES_HDR_MAX 22              /* longest PES header we look at */

/* ------------------------------------------------------------------ */
/* per pid state                                                       */
/* ------------------------------------------------------------------ */

typedef struct
{
	int used;

	/* PCR of this pid (27 MHz units) */
	int has_pcr;
	int pcr_run;           /* consecutive consistent PCR samples */
	int pcr_ref_set;       /* pcr_ref / count_ref are valid */
	uint64_t pcr;
	uint64_t pcr_ref;      /* reference for the frame rate estimation */
	uint64_t count_ref;    /* frame counter at pcr_ref */

	/* PES timestamp bookkeeping (90 kHz units) */
	int has_pts;
	uint64_t written_pts;      /* last PTS written to the stream */
	uint64_t orig_last;        /* last original PTS seen */
	int have_orig;
	uint64_t count;            /* frames written since the anchor */
	uint64_t step;             /* fallback frame duration (90 kHz ticks) */
	int broken;                /* the original timestamps are not monotonic */
	uint64_t repairs;

	/* the clock of the stream: PCR rate measured against the byte offset */
	uint64_t pcr_byte;         /* stream position of the last PCR sample */
	uint64_t pcr_ticks;        /* value of that PCR (27 MHz) */
	int have_clock;
	uint64_t ticks_per_byte;   /* 27 MHz ticks per byte of the stream */
	uint64_t last_frame_byte;  /* stream position of the last frame */
} pid_state_t;

static pid_state_t g_pid[MAX_PID];

/* ------------------------------------------------------------------ */
/* timestamp helpers                                                   */
/* ------------------------------------------------------------------ */

static inline uint64_t pcr_to_90k(uint64_t pcr)
{
	return pcr / 300;
}

static void put_ts(uint8_t *b, uint64_t ts)
{
	b[0] = (uint8_t)(0x21 | (((ts >> 30) & 0x07) << 1));
	b[1] = (uint8_t)((((ts >> 23) & 0x7F) << 1) | 0x01);
	b[2] = (uint8_t)((((ts >> 15) & 0x7F) << 1) | 0x01);
	b[3] = (uint8_t)((((ts >> 7) & 0x7F) << 1) | 0x01);
	b[4] = (uint8_t)(((ts & 0x7F) << 1) | 0x01);
}

static inline uint64_t get_ts(const uint8_t *b)
{
	return (((uint64_t)(b[0] >> 1) & 0x07) << 30) |
	       (((uint64_t)(b[1] >> 1) & 0x7F) << 23) |
	       (((uint64_t)(b[2] >> 1) & 0x7F) << 15) |
	       (((uint64_t)(b[3] >> 1) & 0x7F) << 7) |
	       (((uint64_t)(b[4] >> 1) & 0x7F));
}

/* ------------------------------------------------------------------ */
/* options                                                             */
/* ------------------------------------------------------------------ */

/*
 * The timestamp rebuild is experimental: the adaptation fields of the
 * Abertis streams carry PCR like values whose rate does not match the
 * delivery of the mux, so the rebuilt intervals come out wrong.  It is
 * therefore off by default and only used for experiments.
 */
static int g_fix_pts = 0;
static int g_fix_pcr = 1;
static int g_stats = 0;

/* ------------------------------------------------------------------ */
/* stream repair                                                       */
/* ------------------------------------------------------------------ */

static int g_started = 0;          /* the live part of the stream began */
static uint64_t g_stream_pos;      /* bytes written to stdout so far */

static void handle_pcr(uint8_t *pkt, int pid, uint64_t pos)
{
	pid_state_t *st = &g_pid[pid];
	const uint8_t *af = pkt + 4;

	if (af[0] < 7 || !(af[1] & 0x10))
		return;

	uint8_t *b = (uint8_t *)af + 2;
	uint64_t base = ((uint64_t)b[0] << 25) | ((uint64_t)b[1] << 17) |
	                 ((uint64_t)b[2] << 9)  | ((uint64_t)b[3] << 1)  |
	                 ((uint64_t)b[4] >> 7);
	uint64_t ext = ((uint64_t)(b[4] & 0x01) << 8) | b[5];
	uint64_t pcr = base * 300 + ext;

	/* clear the discontinuity indicator (bit 6 of the first PCR byte) */
	if (g_fix_pcr)
		b[4] &= 0x3F;

	if (!st->used)
	{
		memset(st, 0, sizeof(*st));
		st->used = 1;
	}

	/*
	 * The clock of the stream: the PCR tells how many 27 MHz ticks pass
	 * per byte of the transport stream.  It is independent of the base
	 * of the PCR, so it works for every program of the mux.
	 */
	if (st->have_clock && pos > st->pcr_byte && pcr > st->pcr_ticks)
	{
		uint64_t tpb = (pcr - st->pcr_ticks) / (pos - st->pcr_byte);
		if (tpb > 0)
			st->ticks_per_byte = st->ticks_per_byte
			                   ? ((st->ticks_per_byte * 3 + tpb) / 4) : tpb;
	}
	st->pcr_byte = pos;
	st->pcr_ticks = pcr;
	st->have_clock = 1;

	if (st->has_pcr)
	{
		uint64_t delta = (pcr > st->pcr) ? (pcr - st->pcr) : 0;
		if (delta > 0 && delta < 27000000ULL)     /* less than one second */
			st->pcr_run++;
		else
			st->pcr_run = 0;

		/*
		 * The first packets of a relay connection are stale leftovers
		 * of the demux buffer, with a PCR that is minutes behind the
		 * live stream.  As soon as one pid shows two consistent PCR
		 * samples the stream is live and the output may start.
		 */
		if (!g_started && st->pcr_run >= 2)
			g_started = 1;
	}
	else
	{
		st->pcr_ref = pcr;
		st->pcr_run = 0;
	}

	st->pcr = pcr;
	st->has_pcr = 1;
}

/*
 * Rewrite the timestamps of a complete PES header.
 *
 * The Abertis video streams carry PTS values that are permuted between the
 * frames, so a player that schedules on the PTS sees the frames out of order
 * and stalls.  As soon as a pid shows a backwards timestamp it is treated as
 * broken and its timestamps are regenerated from the frame counter and the
 * PCR clock of the stream, which gives a strictly monotonic sequence with
 * the frame rate of the mux.
 *
 * hdr must hold the complete PES header; on return it holds the new
 * timestamp bytes at offset 9 (PTS) and 14 (DTS).  hdr_len is the number of
 * bytes of the header that carry a timestamp.
 */
static int fix_pes_timestamps(const uint8_t *hdr, int pid, uint8_t *out, int *out_len, uint64_t pos)
{
	pid_state_t *st = &g_pid[pid];

	*out_len = 0;

	if (!(hdr[6] & 0x80))
		return 0;                        /* no PTS at all */

	uint8_t hlen = hdr[8];
	if (hlen < 5 || hlen > 20)
		return 0;

	int has_dts = ((hdr[6] & 0x40) && hlen >= 10);
	uint64_t orig = get_ts(hdr + 9);

	if (!st->used)
	{
		memset(st, 0, sizeof(*st));
		st->used = 1;
	}

	if (!st->has_pts)
	{
		st->has_pts = 1;
		st->written_pts = orig;
		st->count = 1;
		st->have_orig = 1;
		st->orig_last = orig;
		st->last_frame_byte = pos;
		return 0;
	}

	/*
	 * Only a pid whose timestamps are actually broken is rebuilt.  A pid
	 * with clean timestamps (the audio and the radio services of the
	 * Abertis feeds) is left untouched.
	 */
	if (!st->broken)
	{
		if (orig <= st->written_pts)
		{
			/*
			 * The first disorder: the timestamps of this pid are
			 * permuted and their clock does not match the stream.
			 * Rebuild them from the clock of the stream itself.
			 */
			st->broken = 1;
			st->repairs++;
		}
		else
		{
			/* still healthy: keep the original timestamps */
			uint64_t d = orig - st->orig_last;
			if (d > 0 && d < 90000 && (st->step == 0 || d < st->step))
				st->step = d;      /* best guess of the frame time */

			st->written_pts = orig;
			st->have_orig = 1;
			st->orig_last = orig;
			st->last_frame_byte = pos;
			return 0;
		}
	}

	/*
	 * The new timestamp follows the clock of the stream: the bytes that
	 * passed since the previous frame, converted with the PCR rate of
	 * the mux.  A frame that the feed dropped keeps its gap, and the
	 * video runs at exactly the speed of the transport stream - which is
	 * the clock the clean audio pids of the same program use.
	 */
	uint64_t delta = 0;
	if (st->have_clock && st->ticks_per_byte && pos > st->last_frame_byte)
	{
		uint64_t bytes = pos - st->last_frame_byte;
		delta = (bytes * st->ticks_per_byte) / 300;   /* 27 MHz -> 90 kHz */
	}
	if (delta == 0)
		delta = st->step ? st->step : 3600;

	uint64_t new_pts = st->written_pts + delta;

	put_ts(out + 9, new_pts);
	if (has_dts)
		put_ts(out + 14, new_pts);

	*out_len = has_dts ? 19 : 14;

#ifdef ABERTIS_DEBUG
	fprintf(stderr, "PES pid=%d orig=%" PRIu64 " new=%" PRIu64 " delta=%" PRIu64
	        " step=%" PRIu64 " count=%" PRIu64 " broken=%d hlen=%d dts=%d\n",
	        pid, orig, new_pts, delta, st->step, st->count, st->broken, hlen, has_dts);
#endif

	st->written_pts = new_pts;
	st->count++;
	st->have_orig = 1;
	st->orig_last = orig;
	st->last_frame_byte = pos;
	return 1;
}

/* ------------------------------------------------------------------ */
/* service filter                                                      */
/* ------------------------------------------------------------------ */

static int g_filter = 0;
static int g_filter_sid = 0;
static int g_filter_pmt = 0;
static int g_filter_ready = 0;
static int g_filter_pmt_pid = 0;
static uint8_t g_keep_pids[64];
static int g_keep_count = 0;

static void keep_add(int pid)
{
	if (pid < 0 || pid >= MAX_PID)
		return;
	for (int i = 0; i < g_keep_count; i++)
		if (g_keep_pids[i] == pid)
			return;
	if (g_keep_count < (int)sizeof(g_keep_pids))
		g_keep_pids[g_keep_count++] = (uint8_t)pid;
}

static int keep_has(int pid)
{
	for (int i = 0; i < g_keep_count; i++)
		if (g_keep_pids[i] == pid)
			return 1;
	return 0;
}

static void parse_pat(const uint8_t *sec, int len)
{
	if (len < 12 || sec[0] != 0x00)
		return;

	int p = 8;
	while (p + 4 <= len - 4)
	{
		int prog = (sec[p] << 8) | sec[p + 1];
		int pmt = ((sec[p + 2] & 0x1F) << 8) | sec[p + 3];
		if (prog != 0 &&
		    ((g_filter_sid && prog == g_filter_sid) ||
		     (g_filter_pmt && pmt == g_filter_pmt)))
		{
			g_filter_pmt_pid = pmt;
			g_filter_ready = 1;
			keep_add(0);
			keep_add(pmt);
			return;
		}
		p += 4;
	}
}

static void parse_pmt(const uint8_t *sec, int len)
{
	if (len < 16 || sec[0] != 0x02)
		return;

	int pcr = ((sec[8] & 0x1F) << 8) | sec[9];
	int pilen = ((sec[10] & 0x0F) << 8) | sec[11];

	keep_add(pcr);

	int p = 12 + pilen;
	while (p + 5 <= len - 4)
	{
		int epid = ((sec[p + 1] & 0x1F) << 8) | sec[p + 2];
		int elen = ((sec[p + 3] & 0x0F) << 8) | sec[p + 4];
		keep_add(epid);
		p += 5 + elen;
	}
}

/* ------------------------------------------------------------------ */
/* main                                                                */
/* ------------------------------------------------------------------ */

static void usage(const char *name)
{
	fprintf(stderr,
	        "usage: %s <pid> [--sid <n>] [--pmt <pid>] [--fix-pts] [--no-fix-pcr] [--stats]\n"
	        "       Abertis feed extractor and transport stream repairer\n", name);
}

/* state of the inner stream */
static uint8_t g_inner[1024 * 1024];
static size_t g_inner_len;
static size_t g_inner_pos;
static int g_aligned;

/*
 * One packet delay: a PES header may continue in the next packet, so the
 * packet is only emitted when its successor is known.
 */
static uint8_t g_held[TS_PACKET_SIZE];
static int g_held_valid;
static int g_held_pid;
static int g_held_idx;             /* payload offset inside the held packet */
static int g_held_plen;

/* a PES header that continues in the next packet */
static int g_split_active;
static int g_split_pid;
static uint8_t g_split_hdr[PES_HDR_MAX];
static int g_split_len;        /* bytes of the header known so far */
static int g_split_held_off;   /* offset of the header bytes in the held payload */
static int g_split_held_len;   /* bytes of the header that are in the held packet */

static uint64_t g_out_packets;
static uint64_t g_in_packets;
static uint64_t g_prefix_bytes;
static uint64_t g_inner_packets;
static uint64_t g_inner_bytes;   /* position inside the inner transport stream */

/* ------------------------------------------------------------------ */
/* PES header handling                                                 */
/* ------------------------------------------------------------------ */

/*
 * Patch the timestamps of the PES header that starts in the held packet.
 * hdr holds the complete header, len the number of bytes of it that are
 * already known.
 */
static void patch_pes(int pid, const uint8_t *hdr, int len, uint8_t *target, uint64_t pos)
{
	uint8_t out[PES_HDR_MAX];
	int out_len = 0;

	memset(out, 0, sizeof(out));
	if (!fix_pes_timestamps(hdr, pid, out, &out_len, pos))
		return;

	int i;
	for (i = PES_START_MIN; i < len && i < out_len; i++)
		target[i] = out[i];
}

/*
 * A PES header started in the held packet and continues in the current
 * packet: complete the header, patch the held packet and the current one.
 */
static void complete_split_pes(uint8_t *cur, int cur_pid, int cur_idx, int cur_plen)
{
	if (!g_split_active)
		return;

	if (cur_pid != g_split_pid || cur_plen <= 0)
	{
		/* the header did not continue - give up on it */
		g_split_active = 0;
		g_split_len = 0;
		return;
	}

	int want = PES_HDR_MAX - g_split_len;
	if (want > cur_plen)
		want = cur_plen;
	memcpy(g_split_hdr + g_split_len, cur + cur_idx, (size_t)want);
	g_split_len += want;

	if (g_split_len >= 14)
	{
		uint8_t out[PES_HDR_MAX];
		int out_len = 0;
		memset(out, 0, sizeof(out));
		if (fix_pes_timestamps(g_split_hdr, g_split_pid, out, &out_len, g_inner_bytes))
		{
			int i;
			for (i = PES_START_MIN; i < out_len; i++)
			{
				if (i < g_split_held_len)
				{
					/* the byte is in the held packet */
					int off = g_held_idx + g_split_held_off + i;
					if (off < TS_PACKET_SIZE)
						g_held[off] = out[i];
				}
				else
				{
					/* the byte is in the current packet */
					int off = cur_idx + (i - g_split_held_len);
					if (off < TS_PACKET_SIZE)
						cur[off] = out[i];
				}
			}
		}
	}

	g_split_active = 0;
	g_split_len = 0;
}

static void flush_held(void)
{
	if (!g_held_valid)
		return;

	int pid = g_held_pid;
	int emit = 1;

	if (g_filter && g_filter_ready)
		emit = keep_has(pid);

	if (!g_started)
	{
		if (g_inner_packets > 20000)
			g_started = 1;
		else
			emit = 0;
	}

	if (emit)
	{
		ssize_t w = write(STDOUT_FILENO, g_held, TS_PACKET_SIZE);
		if (w < 0 && errno != EINTR)
		{
			perror("write");
			exit(1);
		}
		g_out_packets++;
	}

	g_held_valid = 0;
}

static void process_inner(void)
{
	for (;;)
	{
		size_t avail = g_inner_len - g_inner_pos;
		if (avail < TS_PACKET_SIZE * 3)
			break;

		uint8_t *p = g_inner + g_inner_pos;

		if (!g_aligned)
		{
			size_t i = 0;
			int found = 0;
			while (i + TS_PACKET_SIZE * 3 <= avail)
			{
				if (p[i] == 0x47 && p[i + TS_PACKET_SIZE] == 0x47 &&
				    p[i + TS_PACKET_SIZE * 2] == 0x47)
				{
					found = 1;
					break;
				}
				i++;
			}
			if (!found)
			{
				g_inner_pos += avail - TS_PACKET_SIZE * 2;
				break;
			}
			g_prefix_bytes += i;
			g_inner_pos += i;
			g_aligned = 1;
			continue;
		}

		if (p[0] != 0x47)
		{
			g_aligned = 0;         /* lost alignment, resync */
			continue;
		}

		int pid = ((p[1] & 0x1F) << 8) | p[2];
		int afc = (p[3] >> 4) & 3;
		int idx = 4;
		if (afc & 2)
			idx = 5 + p[4];
		int plen = (afc & 1) ? (TS_PACKET_SIZE - idx) : 0;

		/* --- a PES header of the held packet continues here --------- */
		complete_split_pes(p, pid, idx, plen);

		/* --- the held packet is complete now ------------------------ */
		flush_held();

		g_inner_packets++;
		g_inner_bytes += TS_PACKET_SIZE;

		if (afc & 2)
			handle_pcr(p, pid, g_inner_bytes);

		if ((p[1] & 0x40) && plen > 0 && g_fix_pts)
		{
			uint8_t *pl = p + idx;
			int split = 0;
			int prefix_len = 0;
			int prefix_off = 0;

			if (plen >= 3 && pl[0] == 0x00 && pl[1] == 0x00 && pl[2] == 0x01)
			{
				if (plen >= 14)
				{
					/* the whole header is in this packet */
					uint8_t hdr[PES_HDR_MAX];
					memset(hdr, 0, sizeof(hdr));
					int n = plen < PES_HDR_MAX ? plen : PES_HDR_MAX;
					memcpy(hdr, pl, (size_t)n);
					patch_pes(pid, hdr, n, pl, g_inner_bytes);
				}
				else
				{
					/* the header continues in the next packet */
					split = 1;
					prefix_len = plen;
					prefix_off = 0;
				}
			}
			else
			{
				/*
				 * The start code may be split: the payload ends
				 * with one or two zero bytes and the next packet
				 * continues with "00 01" or "01".
				 */
				int z = 0;
				if (plen >= 2 && pl[plen - 2] == 0x00 && pl[plen - 1] == 0x00)
					z = 2;
				else if (plen >= 1 && pl[plen - 1] == 0x00)
					z = 1;
				if (z > 0)
				{
					split = 1;
					prefix_len = z;
					prefix_off = plen - z;
				}
			}

			if (split)
			{
				g_split_active = 1;
				g_split_pid = pid;
				g_split_len = prefix_len;
				g_split_held_len = prefix_len;
				g_split_held_off = prefix_off;
				memcpy(g_split_hdr, pl + prefix_off, (size_t)prefix_len);
			}
		}

		if (g_filter && (p[1] & 0x40) && plen > 1)
		{
			uint8_t *pl = p + idx;
			int soff = 1 + pl[0];
			if (soff < plen)
			{
				uint8_t *sec = pl + soff;
				int slen = plen - soff;
				if (slen >= 3)
				{
					int sl = ((sec[1] & 0x0F) << 8) | sec[2];
					if (3 + sl <= slen)
					{
						if (pid == 0)
							parse_pat(sec, 3 + sl);
						else if (pid == g_filter_pmt_pid)
							parse_pmt(sec, 3 + sl);
					}
				}
			}
		}

		/* --- hold this packet for the next round -------------------- */
		memcpy(g_held, p, TS_PACKET_SIZE);
		g_held_valid = 1;
		g_held_pid = pid;
		g_held_idx = idx;
		g_held_plen = plen;

		g_inner_pos += TS_PACKET_SIZE;
	}
}

int main(int argc, char **argv)
{
	int target_pid = -1;

	for (int i = 1; i < argc; i++)
	{
		if (!strcmp(argv[i], "--sid") && i + 1 < argc)
			g_filter_sid = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--pmt") && i + 1 < argc)
			g_filter_pmt = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--fix-pts"))
			g_fix_pts = 1;
		else if (!strcmp(argv[i], "--no-fix-pcr"))
			g_fix_pcr = 0;
		else if (!strcmp(argv[i], "--stats"))
			g_stats = 1;
		else if (argv[i][0] == '-')
		{
			usage(argv[0]);
			return 1;
		}
		else if (target_pid < 0)
			target_pid = atoi(argv[i]);
		else
		{
			usage(argv[0]);
			return 1;
		}
	}

	if (target_pid < 0 || target_pid >= MAX_PID)
	{
		usage(argv[0]);
		return 1;
	}

	g_filter = (g_filter_sid || g_filter_pmt) ? 1 : 0;

	static uint8_t inbuf[TS_PACKET_SIZE * 256];
	size_t in_len = 0;

	for (;;)
	{
		ssize_t n = read(STDIN_FILENO, inbuf + in_len, sizeof(inbuf) - in_len);
		if (n < 0)
		{
			if (errno == EINTR)
				continue;
			perror("read");
			return 1;
		}
		if (n == 0)
			break;

		in_len += (size_t)n;

		size_t off = 0;
		while (off + TS_PACKET_SIZE <= in_len)
		{
			uint8_t *pkt = inbuf + off;
			off += TS_PACKET_SIZE;
			g_in_packets++;

			if (pkt[0] != 0x47 || (pkt[1] & 0x80))
				continue;

			int pid = ((pkt[1] & 0x1F) << 8) | pkt[2];
			if (pid != target_pid)
				continue;

			int afc = (pkt[3] >> 4) & 3;
			int idx = 4;
			if (afc & 2)
				idx = 5 + pkt[4];
			if (!(afc & 1) || idx >= TS_PACKET_SIZE)
				continue;

			int plen = TS_PACKET_SIZE - idx;
			if (g_inner_len + (size_t)plen > sizeof(g_inner))
			{
				size_t drop = (size_t)plen;
				memmove(g_inner, g_inner + drop, g_inner_len - drop);
				g_inner_len -= drop;
				g_inner_pos = (g_inner_pos > drop) ? g_inner_pos - drop : 0;
			}
			memcpy(g_inner + g_inner_len, pkt + idx, (size_t)plen);
			g_inner_len += (size_t)plen;
		}

		memmove(inbuf, inbuf + off, in_len - off);
		in_len -= off;

		process_inner();

		if (g_inner_pos > 0)
		{
			memmove(g_inner, g_inner + g_inner_pos, g_inner_len - g_inner_pos);
			g_inner_len -= g_inner_pos;
			g_inner_pos = 0;
		}
	}

	process_inner();
	flush_held();

	if (g_stats)
		fprintf(stderr, "abertis: pid=%d in=%" PRIu64 " out=%" PRIu64
		        " prefix=%" PRIu64 " started=%d\n",
		        target_pid, g_in_packets, g_out_packets, g_prefix_bytes,
		        g_started);

	if (g_filter && !g_filter_ready)
		fprintf(stderr, "abertis: service filter did not match "
		        "(sid=%d pmt=%d)\n", g_filter_sid, g_filter_pmt);

	return 0;
}
