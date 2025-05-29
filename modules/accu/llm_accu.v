module accu(
    input clk,
    input rst_n,
    input [7:0] data_in,
    input valid_in,
    output reg valid_out,
    output reg [9:0] data_out
);

    reg [9:0] accumulator;
    reg [2:0] count;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accumulator <= 10'd0;
            count <= 3'd0;
            valid_out <= 1'b0;
            data_out <= 10'd0;
        end else begin
            if (valid_in) begin
                accumulator <= accumulator + {2'b00, data_in}; // Extend data_in to 10 bits
                count <= count + 1;
                if (count == 3'd3) begin
                    valid_out <= 1'b1;
                    data_out <= accumulator + {2'b00, data_in}; // Add the last input to the accumulator
                    // Reset for the next accumulation
                    accumulator <= 10'd0;
                    count <= 3'd0;
                end else begin
                    valid_out <= 1'b0;
                end
            end else begin
                valid_out <= 1'b0;
            end
        end
    end
endmodule
