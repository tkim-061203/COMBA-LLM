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
    parameter idle = 2'b00;
    parameter s1_red = 2'b01;
    parameter s2_yellow = 2'b10;
    parameter s3_green = 2'b11;

    reg [1:0] state;
    reg [7:0] cnt;
    reg p_red, p_yellow, p_green;

    // State transition logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= idle;
            cnt <= 10; // Reset counter on reset
        end else begin
            case (state)
                idle: state <= s1_red;
                s1_red: if (cnt == 0) state <= s2_yellow; else state <= s1_red;
                s2_yellow: if (cnt == 0) state <= s3_green; else state <= s2_yellow;
                s3_green: if (cnt == 0) state <= s1_red; else state <= s3_green;
            endcase
        end
    end

    // Internal counter logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 10;
        end else begin
            if (pass_request && green && cnt > 10) begin
                cnt <= 10;
            end else if (state == s1_red) begin
                cnt <= 60;
            end else if (state == s2_yellow) begin
                cnt <= 5;
            end else if (state == s3_green) begin
                cnt <= 10;
            end else if (cnt > 0) begin
                cnt <= cnt - 1;
            end
        end
    end

    // Assign output clock
    assign clock = cnt;

    // Output signal logic
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

    // Ensure that the counter is reset correctly when the state changes
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 10;
        end else if (state == s1_red) begin
            cnt <= 60;
        end else if (state == s2_yellow) begin
            cnt <= 5;
        end else if (state == s3_green) begin
            cnt <= 10;
        end
    end

    // Ensure red light is off when not in s1_red state
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            red <= 0;
        end else if (state == s1_red && cnt > 0) begin
            red <= 1;
        end else begin
            red <= 0;
        end
    end

endmodule
