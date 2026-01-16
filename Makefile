DEFINES?=
CFLAGS?=
WORKDIR?=.work
DESIGNS?=$(patsubst ./${WORKDIR}/%, %, $(shell find ./${WORKDIR} -maxdepth 1 -mindepth 1 -type d))
# VERILATOR_WNO=ENUMVALUE DECLFILENAME GENUNNAMED PINCONNECTEMPTY UNOPTFLAT
# VERILATOR_WNO=WIDTHEXPAND UNUSEDSIGNAL
VERILATOR_WNO=DECLFILENAME
# $(patsubst %, -Wno-%, $(VERILATOR_WNO))
VERILATOR_WERROR_MESSAGE=UNDRIVEN MULTIDRIVEN
VERILATOR_CMD=$(shell pwd)/verilator_yosys.sh

define verilating_template
./${WORKDIR}/$(1)/obj_dir/V$(1).h: ${WORKDIR}/$(1)/tb.cpp $(wildcard ${WORKDIR}/$(1)/*.v)
	@ echo "###Verilating for $(1)###"
	cd ${WORKDIR}/$(1) && bash -c "${VERILATOR_CMD} verilator $$$$PWD $(patsubst %, -D%, $(DEFINES)) $(patsubst %,-CFLAGS %, $(CFLAGS)) -Wall -j 0 --trace --x-assign 0 --x-initial 0 -cc --top-module $(1) $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.v, $$^)) --exe $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.cpp, $$^)) -Wno-fatal -Wall $(patsubst %, -Wno-%, $(VERILATOR_WNO)) $(patsubst %, -Werror-%, $(VERILATOR_WERROR_MESSAGE))"
endef

define lintonly_verilating_template
./${WORKDIR}/$(1)/lint: ${WORKDIR}/$(1)/tb.cpp $(wildcard ${WORKDIR}/$(1)/*.v)
	@ echo "###Verilating for $(1)###"
	cd ${WORKDIR}/$(1) && bash -c "${VERILATOR_CMD} verilator $$$$PWD -Wall -j 0 --lint-only --trace --x-assign 0 --x-initial 0 -cc --top-module $(1) $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.v, $$^)) --exe $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.cpp, $$^)) -Wno-fatal -Wall $(patsubst %, -Wno-%, $(VERILATOR_WNO)) $(patsubst %, -Werror-%, $(VERILATOR_WERROR_MESSAGE))"
endef

define lintonly_notb_verilating_template
./${WORKDIR}/$(1)/lintnotb: $(wildcard ${WORKDIR}/$(1)/*.v)
	@ echo "###Verilating for $(1)###"
	@ cd ${WORKDIR}/$(1) && bash -c "${VERILATOR_CMD} verilator $$$$PWD -Wall -j 0 --lint-only --trace --x-assign 0 --x-initial 0 -cc $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.v, $$^)) -Wno-fatal -Wall $(patsubst %, -Wno-%, $(VERILATOR_WNO)) $(patsubst %, -Werror-%, $(VERILATOR_WERROR_MESSAGE))"
endef

define binmake_template
./${WORKDIR}/$(1)/obj_dir/V$(1): ./${WORKDIR}/$(1)/obj_dir/V$(1).h ${WORKDIR}/$(1)/tb.cpp $(wildcard ${WORKDIR}/$(1)/*.v)
	@ echo "###Binary creation for $(1)###"
	cd ${WORKDIR}/$(1) && bash -c "${VERILATOR_CMD} make $$$$PWD -C obj_dir -f V$(1).mk V$(1)"
endef

define run_template
./${WORKDIR}/$(1): ./${WORKDIR}/$(1)/obj_dir/V$(1)
	@ echo "###Run Binary for $(1)###"
	@ cd ${WORKDIR}/$(1) && ./obj_dir/V$(1) ; if [ $$$$? -eq 0 ]; then \
		echo "\033[0;32m ###DESLAPP TESTBENCH $(1) PASS\e[0m"; \
	else \
		echo "\033[0;31m ###DESLAPP TESTBENCH $(1) FAILED\e[0m"; \
	fi
endef

define docker_run_template
./${WORKDIR}/$(1)/docker_run:
	@ bash -c "${VERILATOR_CMD} bash $$$$PWD -c \"./${WORKDIR}/$(1)/obj_dir/V$(1)\""
endef

$(foreach design, $(DESIGNS), $(eval $(call verilating_template,$(design))))
$(foreach design, $(DESIGNS), $(eval $(call binmake_template,$(design))))

.PHONY: $(patsubst %, ${WORKDIR}/%/lintnotb, $(DESIGNS))
$(foreach design, $(DESIGNS), $(eval $(call lintonly_notb_verilating_template,$(design))))

.PHONY: $(patsubst %, ${WORKDIR}/%/lint, $(DESIGNS))
$(foreach design, $(DESIGNS), $(eval $(call lintonly_verilating_template,$(design))))

.PHONY: $(patsubst %, ${WORKDIR}/%, $(DESIGNS))
$(foreach design, $(DESIGNS), $(eval $(call run_template,$(design))))

.PHONY: $(patsubst %, ${WORKDIR}/%/docker_run, $(DESIGNS))
$(foreach design, $(DESIGNS), $(eval $(call docker_run_template,$(design))))