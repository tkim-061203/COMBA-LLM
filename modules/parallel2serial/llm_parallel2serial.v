module parallel2serial(
    input clk,
    input rst_n,
    input [3:0] d,
    output reg valid_out,
    output dout
);

    reg [3:0] data;
    reg [1:0] cnt;

    assign dout = data[3]; // dout is the MSB of data

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt <= 2'b00;
            valid_out <= 0;
            data <= 4'b0000;
        end else begin
            if (cnt == 2'b11) begin
                data <= d; // Load new data
                cnt <= 2'b00; // Reset counter
                valid_out <= 1; // Set valid output
            end else begin
                cnt <= cnt + 1; // Increment counter
                valid_out <= 0; // Clear valid output
                data <= {data[2:0], data[3]}; // Shift data left
            end
        end
    end
endmodule
