import re
import zlib

raw = open("questline.pdf", "rb").read()
texts = []
for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
    try:
        texts.append(zlib.decompress(m.group(1)))
    except Exception:
        pass

blob = b"\n".join(texts).decode("latin-1", errors="ignore")
found = re.findall(r"\((?:[^()\\]|\\.)*\)", blob)
out = " ".join(f[1:-1] for f in found)
out = out.replace("\\(", "(").replace("\\)", ")")
print(out[:8000])
