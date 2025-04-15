module alu(
    input [31:0] a,
    input [31:0] b,
    input [5:0] aluc,
    output reg [31:0] r,
    output zero,
    output carry,
    output negative,
    output overflow,
    output flag
);

    wire [32:0] res;

    // Combinational logic for zero flag
    assign zero = (r == 32'b0);

    // Combinational logic for carry flag
    assign carry = (aluc == 6'b100000 || aluc == 6'b100001 || aluc == 6'b100010 || aluc == 6'b100011) ? res[32] : 1'b0;

    // Combinational logic for overflow flag
    assign overflow = (aluc == 6'b100000) ? ((~a[31] & ~b[31] & r[31]) | (a[31] & b[31] & ~r[31])) :
                       (aluc == 6'b100010) ? ((a[31] & ~b[31] & ~r[31]) | (~a[31] & ~b[31] & r[31])) : 1'b0;

    // Combinational logic for result
    assign res = (aluc == 6'b000000) ? (a << b) :
                 (aluc == 6'b000010) ? (a >> b) :
                 (aluc == 6'b000011) ? ($signed(a) >>> b) :
                 (aluc == 6'b000100) ? (a << b[4:0]) :
                 (aluc == 6'b000110) ? (a >> b[4:0]) :
                 (aluc == 6'b000111) ? ($signed(a) >>> b[4:0]) :
                 (aluc == 6'b100000) ? (a + b) :
                 (aluc == 6'b100001) ? (a + b) :
                 (aluc == 6'b100010) ? (a - b) :
                 (aluc == 6'b100011) ? (a - b) :
                 (aluc == 6'b100100) ? (a & b) :
                 (aluc == 6'b100101) ? (a | b) :
                 (aluc == 6'b100110) ? (a ^ b) :
                 (aluc == 6'b100111) ? ~(a | b) :
                 (aluc == 6'b101010) ? (a < b) :
                 (aluc == 6'b101011) ? ($unsigned(a) < $unsigned(b)) :
                 (aluc == 6'b001111) ? {a[15:0], 16'b0} : 33'b0;

    // Combinational logic for output result
    always @(*) begin
        r = res[31:0];
    end

    // Combinational logic for negative flag
    assign negative = r[31];

    // Combinational logic for flag output
    assign flag = (aluc == 6'b101010) ? (a < b) :
                  (aluc == 6'b101011) ? ($unsigned(a) < $unsigned(b)) : 1'b0;

endmodule
