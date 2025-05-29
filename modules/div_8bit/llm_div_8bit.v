module div_8bit(
    input clk,
    input rst,
    input sign,
    input [7:0] dividend,
    input [7:0] divisor,
    input opn_valid,
    input res_ready,
    output reg res_valid,
    output reg [15:0] result
);

    reg [8:0] divisor_extend;
    reg [8:0] NEG_DIVISOR;
    reg [15:0] SR;
    reg [3:0] cnt;
    reg start_cnt;

    wire [9:0] all_sub_result;
    wire [8:0] sub_result;
    wire [8:0] REMAINER;
    wire [8:0] QUOTIENT;
    wire CO;
    wire [8:0] mux_result;
    wire [6:0] quotient_shift;
    wire [8:0] dividend_abs;
    wire [8:0] final_remainer;
    wire [8:0] final_quotient;
    wire is_final_quotient_sign;

    assign divisor_extend = (sign && divisor[7]) ? {1'b1, divisor} : {1'b0, divisor};
    assign REMAINER = SR[15:8];
    assign QUOTIENT = SR[7:0];
    assign CO = all_sub_result[9];
    assign sub_result = all_sub_result[8:0];
    assign all_sub_result = REMAINER + NEG_DIVISOR;
    assign mux_result = CO ? sub_result : REMAINER;
    assign quotient_shift = SR[7:1];
    assign dividend_abs = (sign && dividend[7]) ? ~dividend + 1'b1 : dividend;
    assign final_remainer = (sign && dividend[7]) ? ~REMAINER + 1'b1 : REMAINER;
    assign final_quotient = (is_final_quotient_sign) ? ~QUOTIENT + 1'b1 : QUOTIENT;
    assign is_final_quotient_sign = sign && (dividend[7] ^ divisor[7]);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            start_cnt <= 0;
            cnt <= 0;
            SR <= 0;
            res_valid <= 0;
        end else begin
            if (opn_valid && !res_valid && !start_cnt) begin
                SR <= {dividend_abs, 1'b0};
                NEG_DIVISOR <= (sign && divisor[7]) ? divisor_extend : ~divisor_extend + 1'b1;
                cnt <= 1;
                start_cnt <= 1;
            end
            if (start_cnt) begin
                if (cnt == 8) begin
                    cnt <= 0;
                    start_cnt <= 0;
                    SR[15:8] <= mux_result;
                    SR[0] <= CO;
                    res_valid <= 1; // Set res_valid when division is complete
                end else begin
                    cnt <= cnt + 1;
                    SR <= {mux_result, quotient_shift, CO, 1'b0};
                end
            end
            if (res_valid && res_ready) begin
                res_valid <= 0;
            end
        end
    end

    always @* begin
        if (res_valid) begin
            result = {final_remainer, final_quotient}; // Update result combinationally
        end else begin
            result = 16'b0; // Ensure result is zero when not valid
        end
    end

endmodule
