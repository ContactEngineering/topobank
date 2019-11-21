.PHONY: all check clean

objects = $(wildcard *.in)
outputs := base.txt local.txt test.txt production.txt
# outputs := $(objects:.in=.txt)

all: $(outputs)

base.txt: base.in
	pip-compile -v --output-file $@ $<

%.txt: %.in base.txt
	pip-compile -v --output-file $@ $<
	# echo "PyCo==0.53.1" >> $@

check:
	@which pip-compile > /dev/null

clean: check
	- rm *.txt
