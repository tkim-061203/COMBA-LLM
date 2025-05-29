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

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stage <= 0;
            o_en <= 0;
            result <= 0;
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
            stage <= 0;
        end else begin
            // Perform addition in pipeline stages
            if (stage < 4) begin
                sum_reg[stage] <= a_reg[stage] + b_reg[stage] + (stage > 0 ? {sum_reg[stage-1][16], 1'b0} : 17'b0);
                stage <= stage + 1;
            end
            if (stage == 3) begin
                result <= {sum_reg[3][16], sum_reg[3][15:0]};
                o_en <= 1;
            end else begin
                o_en <= 0;
            end
        end
    end
endmodule
