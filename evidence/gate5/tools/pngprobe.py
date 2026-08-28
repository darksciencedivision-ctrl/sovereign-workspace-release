"""Minimal stdlib PNG pixel probe (builder tooling). Decodes IHDR/IDAT, unfilters scanlines,
reports selected pixels so screenshots are verified as real renders, not blanks."""
import struct, sys, zlib

def load(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos+8])
        chunk = data[pos+8:pos+8+ln]
        if typ == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"IDAT":
            idat += chunk
        pos += 12 + ln
    w, h, depth, ctype, comp, filt, inter = ihdr
    assert depth == 8 and ctype in (2, 6) and inter == 0, \
        "unsupported PNG: depth=%d ctype=%d inter=%d" % (depth, ctype, inter)
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i-bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i-bpp] if i >= bpp else 0
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    return w, h, bpp, out

def px(buf, w, h, bpp, x, y):
    o = (y*w+x)*bpp
    return tuple(buf[o:o+3])

for path in sys.argv[1:]:
    w, h, bpp, buf = load(path)
    pts = [(w//2, 20), (10, 10), (w//2, h//2), (w//2, h-30)]
    vals = [px(buf, w, h, bpp, x, y) for x, y in pts]
    uniq = len({buf[i] for i in range(0, len(buf), 997)})
    print("%s  %dx%d bpp%d  center-top=%s corner=%s center=%s bottom=%s byte-diversity~%d" %
          (path.split("\\")[-1], w, h, bpp, vals[0], vals[1], vals[2], vals[3], uniq))
