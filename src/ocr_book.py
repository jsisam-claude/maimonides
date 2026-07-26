import subprocess, sys, os, glob
pdf, first, last, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
tmp = "/home/claude/_ocrtmp"
n=0
with open(out, "w") as fo:
    for p in range(first, last+1):
        for old in glob.glob(tmp+"*.png"): os.remove(old)
        subprocess.run(["pdftoppm","-f",str(p),"-l",str(p),"-r","350","-png",pdf,tmp],
                       check=True, stderr=subprocess.DEVNULL)
        imgs = glob.glob(tmp+"*.png")
        if not imgs: continue
        r = subprocess.run(["tesseract",imgs[0],"stdout","-l","heb","--oem","1","--psm","6"],
                           capture_output=True, text=True)
        fo.write(f"\n\n===== PDF3 page {p:03d} =====\n")
        fo.write(r.stdout)
        os.remove(imgs[0]); n+=1
print("OCR pages written:", n)
