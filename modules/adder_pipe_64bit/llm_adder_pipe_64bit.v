module adder_pipe_64bit(
    input wire clk,
    input wire rst_n,
    input wire i_en,
    input wire [63:0] adda,
    input wire [63:0] addb,
    output reg [64:0] result,
    output reg o_en
);

    reg [15:0] a_reg [0:3];
    reg [15:0] b_reg [0:3];
    reg [16:0] sum_reg [0:3];
    reg [1:0] stage;
    reg [16:0] carry;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stage <= 2'b00;
            o_en <= 1'b0;
            result <= 65'b0;
        end else if (i_en) begin
            // Load inputs into registers
            a_reg[0] <= adda[15:0];
            a_reg[1] <= adda[31:16];
            a_reg[2] <= adda[47:32];
            a_reg[3] <= adda[63:48];
            b_reg[0] <= addb[15:0];
            b_reg[1] <= addb[31:16];
            b_reg[2] <= addb[47:32];
            b_reg[3] <= addb[63:48];
            stage <= 2'b01;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sum_reg[0] <= 17'b0;
            sum_reg[1] <= 17'b0;
            sum_reg[2] <= 17'b0;
            sum_reg[3] <= 17'b0;
            carry <= 17'b0;
        end else if (stage == 2'b01) begin
            // Calculate sums for each stage
            sum_reg[0] <= a_reg[0] + b_reg[0];
            carry[0] <= sum_reg[0][16];
            sum_reg[1] <= a_reg[1] + b_reg[1] + carry[0];
            carry[1] <= sum_reg[1][16];
            sum_reg[2] <= a_reg[2] + b_reg[2] + carry[1];
            carry[2] <= sum_reg[2][16];
            sum_reg[3] <= a_reg[3] + b_reg[3] + carry[2];
            stage <= 2'b10;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result <= 65'b0;
            o_en <= 1'b0;
        end else if (stage == 2'b10) begin
            // Output the final result
            result <= {sum_reg[3][16], sum_reg[3][15:0], sum_reg[2][15:0], sum_reg[1][15:0], sum_reg[0][15:0]};
            o_en <= 1'b1;
            stage <= 2'b11;
        end else if (stage == 2'b11) begin
            o_en <= 1'b0; // Reset output enable after one cycle
            stage <= 2'b00; // Reset stage for next operation
        end
    end
endmodule
