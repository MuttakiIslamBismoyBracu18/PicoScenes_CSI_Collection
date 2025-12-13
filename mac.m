function mac(data)
% mac.m
% Extracts all MAC addresses from a PicoScenes CSI file
% and prints TX, RX, and all unique MACs.

    % ---------------------------------------------------------
    % 1. Define MAC conversion helper function
    % ---------------------------------------------------------
    mac2str = @(row) sprintf('%02X:%02X:%02X:%02X:%02X:%02X', row);

    % ---------------------------------------------------------
    % 2. Extract main PicoScenes structure
    % ---------------------------------------------------------
    s = data{1};

    % Extract StandardHeader MAC fields
    A1 = s.StandardHeader.Addr1;   % Receiver (RA)
    A2 = s.StandardHeader.Addr2;   % Transmitter (TA)
    A3 = s.StandardHeader.Addr3;   % BSSID / routing address

    n = size(A1, 1);   % number of frames

    % ---------------------------------------------------------
    % 3. Convert every row to a MAC string
    % ---------------------------------------------------------
    addr1_str = arrayfun(@(i) mac2str(A1(i,:)), 1:n, 'UniformOutput', false);
    addr2_str = arrayfun(@(i) mac2str(A2(i,:)), 1:n, 'UniformOutput', false);
    addr3_str = arrayfun(@(i) mac2str(A3(i,:)), 1:n, 'UniformOutput', false);

    % Combine & find unique
    all_macs = unique([addr1_str, addr2_str, addr3_str]);

    % Remove broadcast
    all_macs = setdiff(all_macs, "FF:FF:FF:FF:FF:FF");

    % ---------------------------------------------------------
    % 4. Print all unique MACs
    % ---------------------------------------------------------
    fprintf("\n==========================================\n");
    fprintf("        Unique MAC Addresses Found\n");
    fprintf("==========================================\n");

    for i = 1:length(all_macs)
        fprintf("%s\n", all_macs{i});
    end

    % ---------------------------------------------------------
    % 5. Identify the first non-broadcast TX/RX pair
    % ---------------------------------------------------------
    non_broadcast_rows = find(any(A2 ~= 255, 2));

    if isempty(non_broadcast_rows)
        fprintf("\nNo non-broadcast TX frames found.\n");
        return;
    end

    first_nb = non_broadcast_rows(1);

    tx_mac = mac2str(A2(first_nb, :));
    rx_mac = mac2str(A1(first_nb, :));

    fprintf("\n==========================================\n");
    fprintf("        Primary TX / RX MAC Addresses\n");
    fprintf("==========================================\n");
    fprintf("Transmitter MAC: %s\n", tx_mac);
    fprintf("Receiver MAC:   %s\n", rx_mac);

    fprintf("\nDone.\n");
end

