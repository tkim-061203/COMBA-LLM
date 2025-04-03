module fsm(
    input wire IN,
    input wire CLK,
    input wire RST,
    output reg MATCH
);

    // State encoding
    parameter s0 = 3'b000;
    parameter s1 = 3'b001;
    parameter s2 = 3'b010;
    parameter s3 = 3'b011;
    parameter s4 = 3'b100;
    parameter s5 = 3'b101;

    reg [2:0] ST_cr; // Current state
    reg [2:0] ST_nt; // Next state

    // Combinational logic for next state
    always @(*) begin
        case (ST_cr)
            s0: ST_nt = (IN == 1'b0) ? s0 : s1;
            s1: ST_nt = (IN == 1'b0) ? s2 : s1;
            s2: ST_nt = (IN == 1'b0) ? s3 : s1;
            s3: ST_nt = (IN == 1'b0) ? s0 : s4;
            s4: ST_nt = (IN == 1'b0) ? s2 : s5;
            s5: ST_nt = (IN == 1'b0) ? s2 : s1;
            default: ST_nt = s0;
        endcase
    end

    // Sequential logic for current state
    always @(posedge CLK or posedge RST) begin
        if (RST) begin
            ST_cr <= s0;
        end else begin
            ST_cr <= ST_nt;
        end
    end

    // Combinational logic for MATCH output
    always @(*) begin
        if (RST) begin
            MATCH = 1'b0;
        end else begin
            MATCH = (ST_cr == s4 && IN == 1'b1) ? 1'b1 : 1'b0;
        end
    end

endmodule
