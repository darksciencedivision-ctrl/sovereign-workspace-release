"""
Secret-emitting fixture for the H-8 four-surface test (R3-2, §7.6.1).

Emits the sentinel SWS_SENTINEL_7f3a9c in every form H-8 requires, plus ANSI CSI sequences, a NUL
byte, and a 10 KB line. Writes raw bytes to stdout so the NUL survives the pipe.

Nothing here is a real credential; the sentinel is a fixed test token.
"""
import sys

SENTINEL = "SWS_SENTINEL_7f3a9c"

FORMS = [
    "API_KEY={}".format(SENTINEL),
    "api-key: {}".format(SENTINEL),
    "apikey={}".format(SENTINEL),
    "token={}".format(SENTINEL),
    "secret: {}".format(SENTINEL),
    "password={}".format(SENTINEL),
    "passwd={}".format(SENTINEL),
    "Authorization: Bearer {}".format(SENTINEL),
    "Bearer {}".format(SENTINEL),
    "GET https://example.invalid/v1/thing?api_key={} HTTP/1.1".format(SENTINEL),
    "GET https://example.invalid/v1/thing?page=2&access_token={} HTTP/1.1".format(SENTINEL),
]


def main():
    out = sys.stdout.buffer
    out.write(b"fixture_noisy start\n")
    for form in FORMS:
        out.write(form.encode("utf-8") + b"\n")

    # ANSI CSI sequences (colour set, cursor move, erase) must be stripped, never interpreted.
    out.write(b"\x1b[31mred\x1b[0m \x1b[2J \x1b[10;20H done\n")
    # OSC sequence.
    out.write(b"\x1b]0;window title\x07after-osc\n")
    # A NUL byte mid-line.
    out.write(b"before-nul\x00after-nul\n")
    # A 10 KB line, with the sentinel embedded in an assignment near the end.
    out.write(b"X" * 10240 + b" trailing token=" + SENTINEL.encode() + b"\n")
    # C1 control range.
    out.write(b"c1-controls:\x85\x9b end\n")
    out.write(b"fixture_noisy done\n")
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
