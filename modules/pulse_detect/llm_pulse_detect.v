module pulse_detect(
    input clk,
    input rst_n,
    input data_in,
    output reg data_out
);

    // State parameters
    parameter s0 = 2'b00; // Initial state, waiting for pulse 0
    parameter s1 = 2'b01; // Waiting for pulse 1
    parameter s2 = 2'b10; // Waiting for pulse 0
    parameter s3 = 2'b11; // Waiting for pulse 1

    reg [1:0] pulse_level1; // Current state register
    reg [1:0] pulse_level2; // Next state register

    // Combinational logic for pulse_level2
    always @(*) begin
        case (pulse_level1)
            s0: pulse_level2 = (data_in == 0) ? s1 : s0;
            s1: pulse_level2 = (data_in == 1) ? s2 : s1;
            s2: pulse_level2 = (data_in == 0) ? s3 : s0;
            s3: pulse_level2 = (data_in == 1) ? s2 : s1;
            default: pulse_level2 = s0;
        endcase
    end

    // Sequential logic for pulse_level1
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pulse_level1 <= s0;
            data_out <= 0;
        end else begin
            pulse_level1 <= pulse_level2;
            // Combinational logic for data_out
            if (pulse_level2 == s2 && data_in == 0) begin
                data_out <= 1;
            end else begin
                data_out <= 0;
            end
        end
    end

endmodule
