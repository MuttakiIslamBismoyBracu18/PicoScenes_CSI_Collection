from picoscenes import Picoscenes
import numpy as np
import sys
import pprint

path = sys.argv[1]

ps = Picoscenes(path)
frames = ps.raw

print("\n========== FRAME KEYS ==========")
print(frames[0].keys())

# Find first CSI frame
csi = None
for f in frames:
    if isinstance(f.get("CSI"), dict):
        csi = f["CSI"]
        print("\n========== FOUND CSI FRAME ==========")
        break

if csi is None:
    print("No CSI found.")
    exit()

print("\n========== csi.keys() ==========")
pprint.pprint(csi.keys())

if "Header" in csi:
    print("\n========== csi['Header'].keys() ==========")
    pprint.pprint(csi["Header"].keys())
else:
    print("\n(no Header key present)")

print("\n========== FULL CSI DICT ==========")
pprint.pprint(csi)
