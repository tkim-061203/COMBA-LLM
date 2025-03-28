module multi_pipe_4bit(
    input clk,
    input rst_n,
    input [3:0] mul_a,
    input [3:0] mul_b,
    output reg [7:0] mul_out
);

    parameter size = 4;
    reg [7:0] partial_products[size-1:0];
    reg [7:0] sum_reg[1:0]; // Only two registers needed for summing
    reg [7:0] final_sum;

    integer i;

    always @(*) begin
        // Generate partial products
        for (i = 0; i < size; i = i + 1) begin
            if (mul_b[i])
                partial_products[i] = mul_a << i;
            else
                partial_products[i] = 8'd0;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset all registers
            sum_reg[0] <= 8'd0;
            sum_reg[1] <= 8'd0;
            final_sum <= 8'd0;
            mul_out <= 8'd0;
        end else begin
            // Add partial products to sum registers
            sum_reg[0] <= partial_products[0] + partial_products[1];
            sum_reg[1] <= partial_products[2] + partial_products[3];
            // Calculate final sum
            final_sum <= sum_reg[0] + sum_reg[1];
            // Update output after one clock cycle
            mul_out <= final_sum;
        end
    end

endmodule
