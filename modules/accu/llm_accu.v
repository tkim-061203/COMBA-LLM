module accu(
    input clk,
    input rst_n,
    input [7:0] data_in,
    input valid_in,
    output reg valid_out,
    output reg [9:0] data_out
);

    reg [7:0] data_buffer [0:3]; // Buffer to hold 4 input data
    reg [1:0] count; // Counter for number of valid inputs

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 0;
            valid_out <= 0;
            data_out <= 0;
        end else begin
            if (valid_in) begin
                if (count < 4) begin
                    data_buffer[count] <= data_in; // Store input data
                    count <= count + 1;
                end
                if (count == 3) begin
                    // Accumulate the 4 data inputs
                    data_out <= data_buffer[0] + data_buffer[1] + data_buffer[2] + data_buffer[3];
                    valid_out <= 1; // Set valid_out for one cycle
                    count <= 0; // Reset count for next accumulation
                end else begin
                    valid_out <= 0; // valid_out is low until 4 inputs are received
                end
            end else begin
                valid_out <= 0; // valid_out is low if valid_in is not asserted
            end
        end
    end
endmodule
