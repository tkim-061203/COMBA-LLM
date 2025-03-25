#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <time.h>
#include <cmath>
#include <iostream>
#include <Vaccu__Syms.h>
#include <assert.h>

using namespace std;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 300
#define VERIF_START_TIME 7
#define myexit(condition, content)   \
    {                                \
        assert(condition &&content); \
    }

vluint64_t sim_time = 0;
vluint64_t tx_data_gen_time = 0;

class accuInTx
{
public:
    /* TODO BEGIN 1 */
    uint8_t clk, rst_n, valid_in, data_in;
    /* TODO END 1 */
};

class accuOutTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t valid_out;
    uint16_t data_out;
    /* TODO END 2 */
};

class accuScb
{
private:
    std::deque<accuInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(accuInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(accuOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in accuScb: empty accuInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        accuInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        switch (in->rst_n)
        {
        case 0:
            if (!(tx->data_out == 0 && tx->valid_out == 0))
            {
                printf("\r\n# TODO 3 Failed at simtime %ld", sim_time);
                printf("\r\n# TODO 3 INPUT TRACE: in->rst_n = 0x%x, in->data_in = 0x%x, in->valid_in = 0x%x", in->rst_n, in->data_in, in->valid_in);
                printf("\r\n# TODO 3 OUTPUT TRACE: tx->data_out = 0x%x, tx->valid_out = 0x%x", tx->data_out, tx->valid_out);

                printf("\r\n");
                fflush(stdout);

                myexit(tx->data_out == 0 && tx->valid_out == 0, "TODO 3 Failed: Reset output logic result of the Verilog module is incorrect")
            }
            break;

        default:
            break;
        }

        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class accuInDrv
{
private:
    Vaccu *dut;

public:
    accuInDrv(Vaccu *dut)
    {
        this->dut = dut;
    }

    void drive(accuInTx *tx)
    {
        /* TODO BEGIN 4 */
        myexit(0, "Delete me first before filling this TODO")
            /* TODO END 4 */

            delete tx;
        dut->eval();
    }
};

class accuInMon
{
private:
    Vaccu *dut;
    accuScb *scb;

public:
    accuInMon(Vaccu *dut, accuScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        accuInTx *tx = new accuInTx();

        /* TODO BEGIN 5 */
        myexit(0, "Delete me first before filling this TODO")
            /* TODO END 5 */

            scb->writeIn(tx);
    }
};

class accuOutMon
{
private:
    Vaccu *dut;
    accuScb *scb;

public:
    accuOutMon(Vaccu *dut, accuScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        accuOutTx *tx = new accuOutTx();

        /* TODO BEGIN 6 */
        myexit(0, "Delete me first before filling this TODO")
            /* TODO END 6 */

            scb->writeOut(tx);
    }
};

accuInTx *rndAluInTx()
{
    accuInTx *tx = new accuInTx();
    /* TODO BEGIN 7 */
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst = 0;

    myexit(0, "Delete me first before filling this TODO")

        else
    {
        delete tx;
        return NULL;
    }
    /* TODO END 7 */

    tx_data_gen_time += tx->rst;
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);
    Vaccu *dut = new Vaccu;

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    accuInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    accuInDrv *drv = new accuInDrv(dut);
    accuScb *scb = new accuScb();
    accuInMon *inMon = new accuInMon(dut, scb);
    accuOutMon *outMon = new accuOutMon(dut, scb);

    /* TODO BEGIN 8 */
    myexit(0, "Delete me first before filling this TODO") while (sim_time < MAX_SIM_TIME)
    {
        dut->clk ^= 1;

        // Do all the driving/monitoring on a positive edge
        if ((dut->clk == 1 || IS_SIM_TIME_IN_RST(sim_time)) && sim_time)
        {

            tx = rndAluInTx();
            // Generate a randomised transaction item of type AluInTx

            // Pass the transaction item to the ALU input interface driver,
            // which drives the input interface based on the info in the
            // transaction item
            drv->drive(tx);

            // Monitor the input interface
            inMon->monitor();

            // Monitor the output interface
            outMon->monitor();
        }
        else
            dut->eval();

        // end of positive edge processing

        m_trace->dump(sim_time);
        sim_time++;
    }
    /* TODO END 8 */
    m_trace->close();
    delete dut;
    delete outMon;
    delete inMon;
    delete scb;
    delete drv;
    exit(EXIT_SUCCESS);
    return 0;
}