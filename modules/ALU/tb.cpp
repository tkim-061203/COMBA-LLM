#include <verilated.h>
#include <verilated_vcd_c.h>
#include <stdio.h>
#include <vector>
#include <time.h>
#include <cmath>
#include <iostream>
#include <VALU__Syms.h>
#include <assert.h>

using namespace std;

VALU *dut = new VALU;

#define IS_SIM_TIME_IN_RST(sim_time) (sim_time >= 3 && sim_time < 6)
#define MAX_SIM_TIME 300
#define VERIF_START_TIME 7
#define MAX_STAGE 100
#define myexit(condition, content)   \
    {                                \
        assert(condition &&content); \
    }

vluint64_t sim_time = 0;
vluint64_t tx_data_gen_time = 0;

#define COMBINATIONAL_LOGIC_EVAL_EN 0
vluint8_t combinational_logic_update = COMBINATIONAL_LOGIC_EVAL_EN;
#define IS_SEQUENTIAL_LOGIC_EVAL(clk, combinational) (clk && (!combinational))
#define IS_SEQUENTIAL_LOGIC_UPDATE(combinational) (!combinational)
#define IS_COMBINATIONAL_LOGIC_EVAL(combinational) (combinational)
#define IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational, cond) (combinational && (cond))

#define LATCH_MANAGEMENT_SELECTOR_VAL(lm) (*lm.selector)
#define LATCH_MANAGEMENT_AFTER_LATCH_VAL(lm) (lm.after_latch_state)
#define LATCH_MANAGEMENT_SELECTOR_ASSIGN(lm, x) (*lm.selector = x)
#define LATCH_MANAGEMENT_SELECTOR_INCREASE(lm, x) (*lm.selector += x)
#define LATCH_MANAGEMENT_SELECTOR_OPERATE_IF_IS_AFTER_LATCH(lm, o, x) \
    if (LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(lm))                 \
    *lm.selector o## = x
#define LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(lm) (lm.selector == &lm.after_latch_state)
#define LATCH_MANAGEMENT_SELECTOR_TO_LATCH_IF_THRESHOLD(lm, threshold, statement1, statement2, statement3) \
    if (LATCH_MANAGEMENT_SELECTOR_VAL(lm) == threshold)                                                    \
    {                                                                                                      \
        if (LATCH_MANAGEMENT_IS_SELECTOR_AFTER_LATCH(lm))                                                  \
        {                                                                                                  \
            LATCH_MANAGEMENT_SELECTOR_TO_LATCH(lm);                                                        \
            LATCH_MANAGEMENT_LATCH_ASSIGN(lm, lm.after_latch_state);                                       \
            statement1                                                                                     \
        }                                                                                                 \
        else                                                                                               \
        {                                                                                                  \
            LATCH_MANAGEMENT_SELECTOR_TO_AFTER_LATCH(lm);                                                  \
            statement2                                                                                     \
        }                                                                                                  \
    }                                                                                                      \
    else                                                                                                   \
    {                                                                                                      \
        statement3                                                                                         \
    }
#define LATCH_MANAGEMENT_SELECTOR_TO_LATCH(lm) (lm.selector = &lm.latch_state)
#define LATCH_MANAGEMENT_SELECTOR_TO_AFTER_LATCH(lm) (lm.selector = &lm.after_latch_state)
#define LATCH_MANAGEMENT_LATCH_ASSIGN(lm, x) (lm.latch_state = lm.after_latch_state)
typedef struct
{
    uint64_t latch_state;
    uint64_t after_latch_state;
    uint64_t *selector;
} latch_management;

class ALUInTx
{
public:
    /* TODO BEGIN 1 */
    myexit(0, "Delete me first before filling this TODO")
    /* TODO END 1 */
};

class ALUOutTx
{
public:
    /* TODO BEGIN 2 */
    myexit(0, "Delete me first before filling this TODO")
    /* TODO END 2 */
};

class ALUInternalTx
{
public:
    /* TODO BEGIN 2 */
    uint8_t a0;
    /* TODO END 2 */
};

// ALUInTx in_tx_ref;
// ALUOutTx out_tx_ref;
// ALUInternalTx internal_tx_ref;

class ALUScb
{
private:
    std::deque<ALUInTx *> in_q;

public:
    // Input interface monitor port
    void writeIn(ALUInTx *tx)
    {
        // Push the received transaction item into a queue for later
        in_q.push_back(tx);
    }

    // Output interface monitor port
    void writeOut(ALUOutTx *tx)
    {
        // We should never get any data from the output interface
        // before an input gets driven to the input interface
        if (in_q.empty())
        {
            std::cout << "Fatal Error in ALUScb: empty ALUInTx queue" << std::endl;
            exit(1);
        }

        // Grab the transaction item from the front of the input item queue
        ALUInTx *in;
        in = in_q.front();
        in_q.pop_front();

        /* TODO BEGIN 3 */
        myexit(0, "Delete me first before filling this TODO")
        /* TODO END 3 */

        delete in;
        delete tx;
    }
};

class ALUInDrv
{
private:
    VALU *dut;

public:
    ALUInDrv(VALU *dut)
    {
        this->dut = dut;
    }

    void drive(ALUInTx *tx)
    {
        /* TODO BEGIN 4 */
        myexit(0, "Delete me first before filling this TODO")
        if (tx != NULL)
        {
            if (COMBINATIONAL_LOGIC_EVAL_EN)
                dut->eval(); // combinational update
            delete tx;
        }
        /* TODO END 4 */
        
        dut->clk ^= IS_SEQUENTIAL_LOGIC_UPDATE(combinational_logic_update);
        dut->eval(); // sequential update
    }
};

class ALUInMon
{
private:
    VALU *dut;
    ALUScb *scb;

public:
    ALUInMon(VALU *dut, ALUScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        ALUInTx *tx = new ALUInTx();

        /* TODO BEGIN 5 */
        myexit(0, "Delete me first before filling this TODO")
        /* TODO END 5 */

        scb->writeIn(tx);
    }
};

class ALUOutMon
{
private:
    VALU *dut;
    ALUScb *scb;

public:
    ALUOutMon(VALU *dut, ALUScb *scb)
    {
        this->dut = dut;
        this->scb = scb;
    }
    void monitor()
    {
        ALUOutTx *tx = new ALUOutTx();
        
        /* TODO BEGIN 6 */
        myexit(0, "Delete me first before filling this TODO")
        /* TODO END 6 */

        scb->writeOut(tx);
    }
};

ALUInTx *rndAluInTx()
{
    ALUInTx *tx = new ALUInTx();
    /* TODO BEGIN 7 */
    uint8_t tx_data_gen_time_increase = IS_COMBINATIONAL_LOGIC_CONDITION_EVAL(combinational_logic_update, !dut->CLK);
    if (IS_SIM_TIME_IN_RST(sim_time))
        tx->rst = 0;
    
    myexit(0, "Delete me first before filling this TODO")
    else if (sim_time >= VERIF_START_TIME)
    {
        tx_data_gen_time += tx_data_gen_time_increase;
        tx_data_gen_time %= MAX_STAGE;
    }
    else
    {
        delete tx;
        return NULL;
    }
    /* TODO END 7 */
    return tx;
}

int main(int argc, char **argv)
{
    srand(time(NULL));
    Verilated::commandArgs(argc, argv);

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    dut->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    ALUInTx *tx;

    // Here we create the driver, scoreboard, input and output monitor blocks
    ALUInDrv *drv = new ALUInDrv(dut);
    ALUScb *scb = new ALUScb();
    ALUInMon *inMon = new ALUInMon(dut, scb);
    ALUOutMon *outMon = new ALUOutMon(dut, scb);

    /* TODO BEGIN 8 */
    myexit(0, "Delete me first before filling this TODO")
    while (sim_time < MAX_SIM_TIME)
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

        // end of positive edge processing

        m_trace->dump(sim_time);
        sim_time++;

        combinational_logic_update ^= COMBINATIONAL_LOGIC_EVAL_EN;
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