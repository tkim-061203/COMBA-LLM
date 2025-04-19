module traffic_light(
    input wire rst_n,
    input wire clk,
    input wire pass_request,
    output reg [7:0] clock,
    output reg red,
    output reg yellow,
    output reg green
);

    parameter idle = 2'b00, s1_red = 2'b01, s2_yellow = 2'b10, s3_green = 2'b11;
    reg [1:0] state;
    reg [5:0] cnt;
    reg p_red, p_yellow, p_green;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= idle;
        end else begin
            case (state)
                idle: state <= s1_red;
                s1_red: if (cnt == 3) state <= s3_green; else state <= s1_red;
                s2_yellow: if (cnt == 3) state <= s1_red; else state <= s2_yellow;
                s3_green: if (cnt == 3) state <= s2_yellow; else state <= s3_green;
            endcase
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 10;
        end else begin
            if (pass_request && green && cnt > 10) begin
                cnt <= 10;
            end else if (!green && p_green) begin
                cnt <= 60;
            end else if (!yellow && p_yellow) begin
                cnt <= 5;
            end else if (!red && p_red) begin
                cnt <= 10;
            end else begin
                cnt <= cnt - 1;
            end
        end
    end

    assign clock = {2'b00, cnt}; // Expanding cnt to 8 bits by concatenating 2'b00

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            p_red <= 0;
            p_yellow <= 0;
            p_green <= 0;
        end else begin
            p_red <= (state == s1_red);
            p_yellow <= (state == s2_yellow);
            p_green <= (state == s3_green);
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            red <= 0;
            yellow <= 0;
            green <= 0;
        end else begin
            red <= p_red;
            yellow <= p_yellow;
            green <= p_green;
        end
    end

endmodule
