
function csi(data, action, varargin)
% CSI Master Utility for PicoScenes CSI Bundles
%
% Usage:
%   csi(data, 'summary')
%   csi(data, 'plot')
%   csi(data, 'plot', 'frames', 1:200)
%   csi(data, 'export', 'basename', 'csi_export')
%   csi(data, 'subcarriers')
%   csi(data, 'identify_ap_sta')
%
% Where:
%   - data is the PicoScenes bundle (e.g., rx_4_251203_030315)
%   - action is one of:
%       'summary'        → full CSI report
%       'plot'           → visualization toolkit
%       'export'         → export CSI to .mat + .npy
%       'subcarriers'    → frequency mapping for tones
%       'identify_ap_sta'→ heuristic AP/STA identification
%
% NOTE: This utility assumes PicoScenes MATLAB Toolbox structure:
%   data{1} is the main struct with fields:
%       .StandardHeader, .RxSBasic, .CSI, etc.

    if nargin < 2
        error('Usage: csi(data, action, ...)');
    end

    s = data{1};  % main PicoScenes struct

    switch lower(action)
        case 'summary'
            summarize_csi(s);

        case 'plot'
            plot_csi(s, varargin{:});

        case 'export'
            export_csi_to_python(s, varargin{:});

        case 'subcarriers'
            extract_subcarriers(s);

        case 'identify_ap_sta'
            identify_ap_sta(s);

        otherwise
            error('Unknown action: %s', action);
    end
end

% ============================================================
function summarize_csi(s)
% summarize_csi.m → full CSI report (NumTx, NumRx, CBW, sampling rate,
% tones, PHY type, etc.)

    c = s.CSI;

    fprintf('\n==========================================\n');
    fprintf('             CSI SUMMARY REPORT\n');
    fprintf('==========================================\n');

    % Basic CSI fields (if they exist)
    print_field(c, 'DeviceType');
    print_field(c, 'FirmwareVersion');
    print_field(c, 'PacketFormat');
    print_field(c, 'CBW');
    print_field(c, 'CarrierFreq');
    print_field(c, 'CarrierFreq2');
    print_field(c, 'SamplingRate');
    print_field(c, 'SubcarrierBandwidth');
    print_field(c, 'NumTones');
    print_field(c, 'NumTx');
    print_field(c, 'NumRx');
    print_field(c, 'NumESS');
    print_field(c, 'NumCSI');

    % Derived CSI stats
    if isfield(c, 'Mag')
        [nFrames, nTones] = size(c.Mag);
        fprintf('Frames (from Mag): %d\n', nFrames);
        fprintf('Tones  (from Mag): %d\n', nTones);
    end

    % Sampling rate from timestamps (RxSBasic.Timestamp)
    if isfield(s, 'RxSBasic') && isfield(s.RxSBasic, 'Timestamp')
        ts = double(s.RxSBasic.Timestamp); % nanoseconds
        ts_sec = ts / 1e9;
        dt = diff(ts_sec);
        fps = 1 / mean(dt);
        fprintf('Derived CSI sampling rate: %.2f Hz\n', fps);
    else
        fprintf('Derived CSI sampling rate: N/A (no RxSBasic.Timestamp)\n');
    end

    % MAC summary
    try
        [ap_mac, sta_mac] = identify_ap_sta(s);
        fprintf('\nGuessed AP MAC:  %s\n', ap_mac);
        fprintf('Guessed STA MAC: %s\n', sta_mac);
    catch
        fprintf('\nAP/STA identification: not available.\n');
    end

    fprintf('==========================================\n\n');
end

% ============================================================
function plot_csi(s, varargin)
% plot_csi.m → visualization toolkit
%
% Options (name/value pairs):
%   'frames'   → vector of frame indices to use (default: 1:min(200, N))
%   'link'     → [rx, tx] pair index for multi-antenna (ignored here since
%                 Mag/Phase are 2D in many PicoScenes logs)

    p = inputParser;
    addParameter(p, 'frames', [], @(x) isnumeric(x) || islogical(x));
    parse(p, varargin{:});
    frames = p.Results.frames;

    c = s.CSI;

    if ~isfield(c, 'Mag') || ~isfield(c, 'Phase')
        error('CSI structure must contain Mag and Phase fields.');
    end

    Amp = c.Mag;
    Phase = c.Phase;

    [N, K] = size(Amp); % N frames, K subcarriers

    if isempty(frames)
        frames = 1:min(200, N);
    else
        frames = frames(frames >= 1 & frames <= N);
    end

    if isempty(frames)
        error('No valid frames selected for plotting.');
    end

    % ---- Plot amplitude of first selected frame ----
    f1 = frames(1);
    figure;
    plot(Amp(f1, :), 'LineWidth', 1.2);
    xlabel('Subcarrier Index');
    ylabel('Amplitude');
    title(sprintf('CSI Amplitude – Frame %d', f1));
    grid on;

    % ---- Plot phase of first selected frame ----
    figure;
    plot(Phase(f1, :), 'LineWidth', 1.2);
    xlabel('Subcarrier Index');
    ylabel('Phase (radians)');
    title(sprintf('CSI Phase – Frame %d', f1));
    grid on;

    % ---- Amplitude over time heatmap ----
    figure;
    imagesc(Amp(frames, :));
    xlabel('Subcarrier Index');
    ylabel('Frame Index (subset)');
    title('CSI Amplitude Over Time');
    colorbar;

    % ---- Phase over time heatmap ----
    figure;
    imagesc(Phase(frames, :));
    xlabel('Subcarrier Index');
    ylabel('Frame Index (subset)');
    title('CSI Phase Over Time');
    colorbar;
end

% ============================================================
function extract_subcarriers(s)
% extract_subcarriers.m → frequency mapping for tones

    c = s.CSI;

    if ~isfield(c, 'SubcarrierIndex') || ~isfield(c, 'SubcarrierBandwidth')
        error('CSI structure must contain SubcarrierIndex and SubcarrierBandwidth.');
    end

    idx = double(c.SubcarrierIndex);
    delta_f = double(c.SubcarrierBandwidth); % Hz

    freq_offsets_hz = idx * delta_f; % offset from center frequency (Hz)

    fprintf('\n==========================================\n');
    fprintf('        Subcarrier Frequency Mapping\n');
    fprintf('==========================================\n');
    fprintf('Subcarrier spacing: %.2f kHz\n', delta_f / 1e3);
    fprintf('Number of tones:    %d\n\n', numel(idx));

    T = table(idx(:), freq_offsets_hz(:)/1e6, ...
              'VariableNames', {'SubcarrierIndex', 'FreqOffsetMHz'});
    disp(T(1:min(20,height(T)), :)); % show first few

    % Optional plot: mean amplitude vs frequency
    if isfield(c, 'Mag')
        Amp = c.Mag;
        mean_amp = mean(Amp, 1);
        figure;
        plot(freq_offsets_hz/1e6, mean_amp, 'LineWidth', 1.2);
        xlabel('Frequency Offset (MHz)');
        ylabel('Mean Amplitude');
        title('Mean CSI Amplitude vs Frequency Offset');
        grid on;
    end
end

% ============================================================
function export_csi_to_python(s, varargin)
% export_csi_to_python.m → .mat → .npy converter
%
% Saves:
%   basename.mat      → MATLAB file with H, Amp, Phase, subcarriers, ts
%   basename_H.npy    → complex CSI (double, real/imag stacked)
%   basename_Amp.npy  → amplitude (double)
%   basename_Phase.npy→ phase (double)

    p = inputParser;
    addParameter(p, 'basename', 'csi_export', @ischar);
    parse(p, varargin{:});
    basename = p.Results.basename;

    c = s.CSI;

    if ~isfield(c, 'CSI') || ~isfield(c, 'Mag') || ~isfield(c, 'Phase')
        error('CSI structure must contain CSI, Mag, and Phase fields.');
    end

    H = c.CSI;
    Amp = c.Mag;
    Phase = c.Phase;

    % Timestamps (if available)
    ts_sec = [];
    if isfield(s, 'RxSBasic') && isfield(s.RxSBasic, 'Timestamp')
        ts = double(s.RxSBasic.Timestamp); % ns
        ts_sec = ts / 1e9;
    end

    subcarriers = [];
    if isfield(c, 'SubcarrierIndex')
        subcarriers = c.SubcarrierIndex;
    end

    fprintf('\nExporting CSI to %s.mat and .npy files...\n', basename);

    % Save .mat (easy to load in Python via scipy.io.loadmat)
    save([basename '.mat'], 'H', 'Amp', 'Phase', 'subcarriers', 'ts_sec', '-v7.3');

    % Save .npy (simple writer, supports 2D double arrays)
    % For complex H, we save real/imag stacked along 3rd dimension.
    H_reim = cat(3, real(H), imag(H)); % shape: [N, K, 2]

    write_npy([basename '_H.npy'], H_reim);
    write_npy([basename '_Amp.npy'], Amp);
    write_npy([basename '_Phase.npy'], Phase);

    fprintf('Done.\n\n');
    fprintf('Python loading example:\n');
    fprintf('  import numpy as np\n');
    fprintf('  H = np.load("%s_H.npy")   # shape: (N, K, 2)\n', basename);
    fprintf('  Amp = np.load("%s_Amp.npy")\n', basename);
    fprintf('  Phase = np.load("%s_Phase.npy")\n', basename);
    fprintf('  # Or use scipy.io.loadmat("%s.mat")\n\n', basename);
end

% ============================================================
function [ap_mac, sta_mac] = identify_ap_sta(s)
% identify_ap_sta.m → automatically detect AP vs STA roles (heuristic)
%
% Returns:
%   ap_mac  → guessed AP MAC address (string)
%   sta_mac → guessed STA MAC address (string)

    mac2str = @(row) sprintf('%02X:%02X:%02X:%02X:%02X:%02X', row);
    broadcast = 'FF:FF:FF:FF:FF:FF';

    A1 = s.StandardHeader.Addr1; % RA
    A2 = s.StandardHeader.Addr2; % TA
    A3 = s.StandardHeader.Addr3; % often BSSID in infrastructure mode

    n = size(A1,1);

    addr1_str = arrayfun(@(i) mac2str(A1(i,:)), 1:n, 'UniformOutput', false);
    addr2_str = arrayfun(@(i) mac2str(A2(i,:)), 1:n, 'UniformOutput', false);
    addr3_str = arrayfun(@(i) mac2str(A3(i,:)), 1:n, 'UniformOutput', false);

    % Heuristic AP candidate: most frequent MAC in Addr3
    [uniqA3, ~, idx3] = unique(addr3_str);
    countsA3 = accumarray(idx3, 1);
    [~, order3] = sort(countsA3, 'descend');
    ap_mac = uniqA3{order3(1)};

    % Remove broadcast if it somehow appears
    if strcmp(ap_mac, broadcast) && numel(order3) > 1
        ap_mac = uniqA3{order3(2)};
    end

    % STA candidate: most frequent non-AP, non-broadcast MAC appearing in A1/A2
    all_macs = [addr1_str, addr2_str];
    all_macs = all_macs(:);
    all_macs = setdiff(all_macs, {broadcast, ap_mac});

    [uniqAll, ~, idxAll] = unique(all_macs);
    countsAll = accumarray(idxAll, 1);
    [~, orderAll] = sort(countsAll, 'descend');

    sta_mac = uniqAll{orderAll(1)};

    fprintf('\nAP/STA Identification (Heuristic):\n');
    fprintf('  AP  candidate: %s\n', ap_mac);
    fprintf('  STA candidate: %s\n\n', sta_mac);
end

% ============================================================
function print_field(c, fieldname)
% Helper to safely print a field if it exists
    if isfield(c, fieldname)
        val = c.(fieldname);
        if isnumeric(val)
            if isscalar(val)
                fprintf('%s: %g\n', fieldname, val);
            else
                sz = size(val);
                fprintf('%s: numeric [%s]\n', fieldname, num2str(sz));
            end
        elseif ischar(val) || isstring(val)
            fprintf('%s: %s\n', fieldname, string(val));
        else
            sz = size(val);
            fprintf('%s: [%s %s]\n', fieldname, class(val), num2str(sz));
        end
    end
end

% ============================================================
function write_npy(filename, array)
% Minimal NumPy .npy writer for 2D or 3D double arrays (little-endian).
% Supports dtype '<f8' (float64).

    if ~isa(array, 'double')
        array = double(array);
    end

    shape = size(array);
    nd = numel(shape);

    % Build header dict
    shape_str = '(';
    for i = 1:nd
        if i < nd
            shape_str = sprintf('%s%d, ', shape_str, shape(i));
        else
            if nd == 1
                shape_str = sprintf('%s%d,', shape_str, shape(i)); % single dim needs trailing comma
            else
                shape_str = sprintf('%s%d', shape_str, shape(i));
            end
        end
    end
    shape_str = [shape_str, ')'];

    header_dict = sprintf('{' ...
        '''descr'': ''<f8'', ' ...
        '''fortran_order'': False, ' ...
        '''shape'': %s, }', shape_str);

    % NPY header format v1.0
    magic = char([147, 'NUMPY']); %#ok<CHARTEN>
    major = uint8(1);
    minor = uint8(0);

    % Pad header to be aligned to 16 bytes
    header = [header_dict, char(10)]; % newline at end
    header_len = length(header);
    pad_len = 16 - mod(10 + header_len, 16); % 10 = magic(6) + 2 version + 2 header_len
    if pad_len == 16
        pad_len = 0;
    end
    header = [header_dict, repmat(' ', 1, pad_len), char(10)];
    header_len = length(header);

    fid = fopen(filename, 'w');
    if fid == -1
        error('Could not open %s for writing.', filename);
    end

    cleanup = onCleanup(@() fclose(fid));

    fwrite(fid, magic, 'uint8');
    fwrite(fid, major, 'uint8');
    fwrite(fid, minor, 'uint8');

    fwrite(fid, uint16(header_len), 'uint16'); % little-endian by default

    fwrite(fid, header, 'char');

    % Write data in C order
    fwrite(fid, array(:), 'double');
end
