module edge_detect(
    input wire clk,
    input wire rst_n,
    input wire a,
    output reg rise,
    output reg down
);

    reg a_prev;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rise <= 0;
            down <= 0;
            a_prev <= 0;
        end else begin
            rise <= 0; // Default to 0
            down <= 0; // Default to 0
            if (a && !a_prev) begin
                rise <= 1; // Rising edge detected
            end
            if (!a && a_prev) begin
                down <= 1; // Falling edge detected
            end
            a_prev <= a; // Update previous state
        end
    end

endmodule
