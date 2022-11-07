.PHONY: all check clean

outputs := local.txt production.txt
setup_files := ../setup.cfg ../setup.py

all: $(outputs)

local.txt: $(setup_files)
	pip-compile --extra dev -v --output-file $@ ../setup.py

production.txt: $(setup_files)
	pip-compile -v --output-file $@ ../setup.py

check:
	@which pip-compile > /dev/null

clean: check
	- rm *.txt
