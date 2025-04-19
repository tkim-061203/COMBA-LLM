module multi_pipe_4bit #(parameter size = 4) (
    input wire clk,
    input wire rst_n,
    input wire [size-1:0] mul_a,
    input wire [size-1:0] mul_b,
    output reg [2*size-1:0] mul_out
);

    reg [2*size-1:0] partial_products [0:size-1];
    reg [2*size-1:0] sum_reg [0:size/2-1];
    integer i;

    always @(*) begin
        // Generate partial products
        for (i = 0; i < size; i = i + 1) begin
            if (mul_b[i])
                partial_products[i] = mul_a << i; // Correctly shift mul_a without zero extension
            else
                partial_products[i] = 'd0;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset condition
            for (i = 0; i < size/2; i = i + 1) begin
                sum_reg[i] <= 'd0;
            end
            mul_out <= 'd0;
        end else begin
            // Add partial products
            for (i = 0; i < size/2; i = i + 1) begin
                sum_reg[i] <= partial_products[2*i] + partial_products[2*i + 1];
            end
            // Calculate final product
            mul_out <= 'd0;
            for (i = 0; i < size/2; i = i + 1) begin
                mul_out <= mul_out + sum_reg[i];
            end
            // Ensure mul_out is updated after one clock cycle
            mul_out <= sum_reg[0] + sum_reg[1]; // Directly assign the final product
        end
    end
endmodule
