
module adder_8bit (
   input [7:0] a,
   input [7:0] b,
   input cin,
   output reg [7:0] sum,
   output reg cout
);

assign cout = cin;

always @* begin
   sum[0] = a[0] ^ b[0] ^ cin;
   cout = cin;
   for (int i = 1; i < 8; i++) begin
      assign sum[i] = a[i] ^ b[i] ^ cout;
      assign cout = a[i] & b[i] | a[i] & cout | b[i] & cout;
   end
end

endmodule
