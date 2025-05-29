module serial2parallel(
    input wire clk,
    input wire rst_n,
    input wire din_serial,
    input wire din_valid,
    output reg [7:0] dout_parallel,
    output reg dout_valid
);

    reg [3:0] cnt;
    reg [7:0] din_tmp;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 0;
            din_tmp <= 0;
            dout_parallel <= 0;
            dout_valid <= 0;
        end else begin
            if (din_valid && cnt < 8) begin
                din_tmp <= {din_tmp[6:0], din_serial};
                cnt <= cnt + 1;
            end
            if (cnt == 7) begin
                dout_parallel <= din_tmp;
                dout_valid <= 1;
                cnt <= 0; // Reset counter after 8 bits
            end else begin
                dout_valid <= 0;
            end
        end
    end
endmodule
