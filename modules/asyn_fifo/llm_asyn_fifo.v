module dual_port_RAM #(parameter DEPTH = 16, parameter WIDTH = 8) (input wclk, input wen, input [$clog2(DEPTH)-1:0] waddr, input [WIDTH-1:0] wdata, input rclk, input ren, input [$clog2(DEPTH)-1:0] raddr, output reg [WIDTH-1:0] rdata);
    reg [WIDTH-1:0] RAM_MEM [0:DEPTH-1];
    always @(posedge wclk) begin
        if (wen) begin
            RAM_MEM[waddr] <= wdata;
        end
    end
    always @(posedge rclk) begin
        if (ren) begin
            rdata <= RAM_MEM[raddr];
        end
    end
endmodule

module asyn_fifo #(parameter WIDTH = 8, parameter DEPTH = 16) (input wclk, input rclk, input wrstn, input rrstn, input winc, input rinc, input [WIDTH-1:0] wdata, output reg wfull, output reg rempty, output reg [WIDTH-1:0] rdata);
    localparam ADDR_WIDTH = $clog2(DEPTH);
    reg [ADDR_WIDTH:0] raddr_bin;
    wire [ADDR_WIDTH-1:0] raddr_gray;
    reg [ADDR_WIDTH:0] rptr;
    reg [ADDR_WIDTH:0] rptr_buff;
    reg [ADDR_WIDTH:0] rptr_syn;
    wire ren;
    reg [ADDR_WIDTH:0] waddr_bin;
    wire [ADDR_WIDTH-1:0] waddr_gray;
    reg [ADDR_WIDTH:0] wptr;
    reg [ADDR_WIDTH:0] wptr_buff;
    reg [ADDR_WIDTH:0] wptr_syn;
    wire wen;

    // Sequential Logic for Read Address
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            raddr_bin <= 0;
        end else if (!rempty && rinc) begin
            raddr_bin <= raddr_bin + 1;
        end
    end

    // Combinational Logic for Read Address Gray Code
    assign raddr_gray = raddr_bin ^ (raddr_bin >> 1);

    // Sequential Logic for Read Pointer
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            rptr <= 0;
        end else begin
            rptr <= raddr_gray;
        end
    end

    // Sequential Logic for Read Pointer Buffer
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            rptr_buff <= 0;
        end else begin
            rptr_buff <= rptr;
        end
    end

    // Sequential Logic for Read Pointer Synchronization
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            rptr_syn <= 0;
        end else begin
            rptr_syn <= rptr_buff;
        end
    end

    // Combinational Logic for Read Enable
    assign ren = rinc && !rempty;

    // Sequential Logic for Write Address
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            waddr_bin <= 0;
        end else if (!wfull && winc) begin
            waddr_bin <= waddr_bin + 1;
        end
    end

    // Combinational Logic for Write Address Gray Code
    assign waddr_gray = waddr_bin ^ (waddr_bin >> 1);

    // Sequential Logic for Write Pointer
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            wptr <= 0;
        end else begin
            wptr <= waddr_gray;
        end
    end

    // Combinational Logic for Write Full Signal
    always @(*) begin
        wfull = (wptr == {~rptr_syn[ADDR_WIDTH:ADDR_WIDTH-2], rptr_syn[ADDR_WIDTH-3:0]});
    end

    // Sequential Logic for Write Pointer Buffer
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            wptr_buff <= 0;
        end else begin
            wptr_buff <= wptr;
        end
    end

    // Sequential Logic for Write Pointer Synchronization
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            wptr_syn <= 0;
        end else begin
            wptr_syn <= wptr_buff;
        end
    end

    // Combinational Logic for Write Enable
    assign wen = winc && !wfull;

    // Combinational Logic for Read Empty Signal
    always @(*) begin
        rempty = (rptr == wptr_syn);
    end

    // Instantiate Dual-Port RAM
    dual_port_RAM #(.DEPTH(DEPTH), .WIDTH(WIDTH)) ram (
        .wclk(wclk),
        .wen(wen),
        .waddr(waddr_bin[ADDR_WIDTH-1:0]),
        .wdata(wdata),
        .rclk(rclk),
        .ren(ren),
        .raddr(raddr_bin[ADDR_WIDTH-1:0]),
        .rdata(rdata)
    );
endmodule
