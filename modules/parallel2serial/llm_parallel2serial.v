module parallel2serial(
    input clk,
    input rst_n,
    input [3:0] d,
    output reg valid_out,
    output reg dout
);

    reg [3:0] data;
    reg [1:0] cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 2'b00;
            valid_out <= 0;
            dout <= 0;
            data <= 0;
        end else begin
            if (cnt == 2'b00) begin
                data <= d;
                cnt <= 2'b01;
                valid_out <= 1;
            end else if (cnt < 2'b11) begin
                dout <= data[3]; // Output the MSB
                data <= {data[2:0], 1'b0}; // Shift left and fill LSB with 0
                cnt <= cnt + 1;
                valid_out <= 0;
            end else if (cnt == 2'b11) begin
                dout <= data[3]; // Output the last bit
                data <= {data[2:0], 1'b0}; // Shift left
                cnt <= cnt + 1;
                valid_out <= 0;
            end else begin
                valid_out <= 0; // Ensure valid_out is 0 after the last bit
            end
        end
    end

endmodule
