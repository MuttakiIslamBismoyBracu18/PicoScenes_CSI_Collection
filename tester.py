import numpy as np
from picoscenes import Picoscenes

ps = Picoscenes("rx_4_251203_030315.csi")
frames = ps.raw

for f in frames:
    if "CSI" in f:
        print(f["CSI"].keys())
        break
