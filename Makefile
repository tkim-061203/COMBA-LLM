DEFINES?=
WORKDIR?=.work
DESIGNS=$(patsubst ./${WORKDIR}/%, %, $(shell find ./${WORKDIR} -maxdepth 1 -mindepth 1 -type d))

define verilating_template
./${WORKDIR}/$(1)/obj_dir/V$(1).h: ${WORKDIR}/$(1)/tb.cpp $(wildcard ${WORKDIR}/$(1)/*.v)
	@ echo "###Verilating for $(1)###"
	@ cd ${WORKDIR}/$(1) && bash -c "verilator_yosys.sh verilator $$$$PWD $(patsubst %, -D%, $(DEFINES)) -Wall -j 0 --trace --x-assign unique --x-initial unique -cc --top-module $(1) $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.v, $$^)) --exe $$(patsubst ${WORKDIR}/$(1)/%, %, $$(filter %.cpp, $$^)) -Wno-ENUMVALUE -Wno-DECLFILENAME"
endef

define binmake_template
./${WORKDIR}/$(1)/obj_dir/V$(1): ./${WORKDIR}/$(1)/obj_dir/V$(1).h
	@ echo "###Binary creation for $(1)###"
	cd ${WORKDIR}/$(1) && bash -c "verilator_yosys.sh make $$$$PWD -C obj_dir -f V$(1).mk V$(1)"
endef

define run_template
./${WORKDIR}/$(1): ./${WORKDIR}/$(1)/obj_dir/V$(1)
	@ echo "###Run Binary for $(1)###"
	@ cd ${WORKDIR}/$(1) && ./obj_dir/V$(1) ; if [ $$$$? -eq 0 ]; then \
		echo "\033[0;32m Teshbench $(1) PASS\e[0m"; \
	else \
		echo "\033[0;31m Teshbench $(1) FAILED\e[0m"; \
	fi
endef
# all:
# 	@echo ${DESIGNS}
# 	# @echo $(foreach design, $(DESIGNS), $(call verilating_template,$(design)))
# 	@exit 1;

$(foreach design, $(DESIGNS), $(eval $(call verilating_template,$(design))))
$(foreach design, $(DESIGNS), $(eval $(call binmake_template,$(design))))

.PHONY: $(patsubst %, ${WORKDIR}/%, $(DESIGNS))
$(foreach design, $(DESIGNS), $(eval $(call run_template,$(design))))