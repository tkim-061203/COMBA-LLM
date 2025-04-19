module multi_pipe_8bit(
    input clk,
    input rst_n,
    input mul_en_in,
    input [7:0] mul_a,
    input [7:0] mul_b,
    output reg mul_en_out,
    output reg [15:0] mul_out
);

    reg [7:0] mul_a_reg;
    reg [7:0] mul_b_reg;
    reg [2:0] mul_en_out_reg;
    wire [15:0] temp [7:0];
    reg [15:0] sum;
    reg [15:0] mul_out_reg;

    // Sequential logic for mul_a_reg
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_a_reg <= 8'b0;
        end else if (mul_en_in) begin
            mul_a_reg <= mul_a;
        end else begin
            mul_a_reg <= 8'b0;
        end
    end

    // Sequential logic for mul_b_reg
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_b_reg <= 8'b0;
        end else if (mul_en_in) begin
            mul_b_reg <= mul_b;
        end else begin
            mul_b_reg <= 8'b0;
        end
    end

    // Combinational logic for partial product generation
    generate
        genvar i;
        for (i = 0; i < 8; i = i + 1) begin: partial_products
            assign temp[i] = (mul_b_reg[i]) ? ({8'b0, mul_a_reg} << i) : 16'b0;
        end
    endgenerate

    // Sequential logic for output enable
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_en_out_reg <= 3'b0;
            mul_en_out <= 1'b0;
        end else begin
            mul_en_out_reg <= {mul_en_out_reg[1:0], mul_en_in};
            mul_en_out <= mul_en_out_reg[2];
        end
    end

    // Sequential logic for sum calculation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sum <= 16'b0;
        end else begin
            sum <= temp[0] + temp[1] + temp[2] + temp[3] + temp[4] + temp[5] + temp[6] + temp[7];
        end
    end

    // Sequential logic for final product calculation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_out_reg <= 16'b0;
        end else begin
            mul_out_reg <= sum;
        end
    end

    // Output assignment
    always @(*) begin
        if (mul_en_out) begin
            mul_out = mul_out_reg;
        end else begin
            mul_out = 16'b0;
        end
    end

endmodule
