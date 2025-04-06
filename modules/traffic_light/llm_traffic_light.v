module traffic_light(
    input wire rst_n,
    input wire clk,
    input wire pass_request,
    output reg [7:0] clock,
    output reg red,
    output reg yellow,
    output reg green
);

    // State parameters
    parameter idle = 0, s1_red = 1, s2_yellow = 2, s3_green = 3;
    reg [1:0] state, next_state;
    reg [7:0] cnt;
    reg p_red, p_yellow, p_green;

    // State transition logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= idle;
        end else begin
            state <= next_state;
        end
    end

    // Counter logic
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

    // Next state logic
    always @(*) begin
        case (state)
            idle: next_state = s1_red;
            s1_red: next_state = (cnt == 3) ? s3_green : s1_red;
            s2_yellow: next_state = (cnt == 3) ? s1_red : s2_yellow;
            s3_green: next_state = (cnt == 3) ? s2_yellow : s3_green;
            default: next_state = idle;
        endcase
    end

    // Output logic
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

    // Assign outputs
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

    // Assign internal counter to output clock
    assign clock = cnt;

endmodule
