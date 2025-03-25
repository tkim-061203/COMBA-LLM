module adder_pipe_64bit(
    input wire clk,
    input wire rst_n,
    input wire i_en,
    input wire [63:0] adda,
    input wire [63:0] addb,
    output reg [64:0] result,
    output reg o_en
);

    // Intermediate registers for pipelining
    reg [63:0] a_reg [0:3];
    reg [63:0] b_reg [0:3];
    reg [64:0] sum_reg [0:3];
    reg [1:0] stage;

    // Pipeline stage control
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stage <= 2'b00;
            o_en <= 1'b0;
        end else if (i_en) begin
            // Load inputs into registers
            a_reg[stage] <= adda;
            b_reg[stage] <= addb;
            // Calculate sum for the current stage
            sum_reg[stage] <= a_reg[stage] + b_reg[stage];
            // Update output enable signal
            o_en <= (stage == 2'b11);
            // Move to the next stage
            stage <= stage + 1;
        end
    end

    // Output result based on the last stage
    always @(posedge clk) begin
        if (o_en) begin
            result <= sum_reg[3];
        end
    end

endmodule
