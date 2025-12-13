%% Load CSI structs
csi_struct = data{1};   % main PicoScenes struct

%% Extract CSI
H = csi_struct.CSI.CSI;      % complex CSI (frames × subcarriers)
Amp = csi_struct.CSI.Mag;    % amplitude
Phase = csi_struct.CSI.Phase;% phase

%% Plot amplitude of first frame
figure;
plot(Amp(1,:));
xlabel("Subcarrier Index");
ylabel("Amplitude");
title("CSI Amplitude – Frame 1");

%% Plot phase of first frame
figure;
plot(Phase(1,:));
xlabel("Subcarrier Index");
ylabel("Phase (radians)");
title("CSI Phase – Frame 1");

%% Amplitude over time (heatmap)
figure;
imagesc(Amp);
xlabel("Subcarrier Index");
ylabel("Frame Index");
title("CSI Amplitude Over Time");
colorbar;

%% Extract timestamps
ts = double(csi_struct.RxSBasic.Timestamp); % ns
ts_sec = ts / 1e9; % convert to seconds

%% Compute sampling rate (FPS)
dt = diff(ts_sec);
fps = 1 / mean(dt);

fprintf("Mean CSI FPS: %.2f Hz\n", fps);

