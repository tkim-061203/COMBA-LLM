module JC_counter(
    input clk,
    input rst_n,
    output reg [63:0] Q
);

    // Combinational logic for increment and decrement shifting
    wire [63:0] Q_right_increament_shifting;
    wire [63:0] Q_right_decreament_shifting;

    assign Q_right_increament_shifting = {1'b1, Q[63:1]};
    assign Q_right_decreament_shifting = {1'b0, Q[63:1]};

    // Sequential logic for counter operation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            Q <= 64'b0; // Reset condition
        end else begin
            if (Q[0] == 1'b0) begin
                Q <= Q_right_increament_shifting; // Increment
            end else begin
                Q <= Q_right_decreament_shifting; // Decrement
            end
        end
    end
endmodule
