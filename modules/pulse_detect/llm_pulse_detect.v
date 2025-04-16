module pulse_detect(
    input clk,
    input rst_n,
    input data_in,
    output reg data_out
);

    // State encoding
    parameter s0 = 2'b00; // Initial state, waiting for pulse 0
    parameter s1 = 2'b01; // Waiting for pulse 1
    parameter s2 = 2'b10; // Waiting for pulse 0
    parameter s3 = 2'b11; // Waiting for pulse 1

    reg [1:0] pulse_level1; // Current state
    wire [1:0] pulse_level2; // Next state

    // Combinational logic for pulse_level2
    assign pulse_level2 = (pulse_level1 == s0) ? (data_in ? s0 : s1) :
                          (pulse_level1 == s1) ? (data_in ? s2 : s1) :
                          (pulse_level1 == s2) ? (data_in ? s0 : s3) :
                          (pulse_level1 == s3) ? (data_in ? s2 : s1) : s0;

    // Sequential logic for pulse_level1
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pulse_level1 <= s0; // Reset to initial state
        end else begin
            pulse_level1 <= pulse_level2; // Update state
        end
    end

    // Combinational logic for data_out
    always @(*) begin
        if (!rst_n) begin
            data_out = 0; // Reset output
        end else begin
            data_out = (pulse_level2 == s2 && data_in == 0) ? 1 : 0; // Set output based on pulse detection
        end
    end

endmodule
