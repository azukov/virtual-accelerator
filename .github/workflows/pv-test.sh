. .po3_va_previous/bin/activate
virtual_accelerator --print_pvs > old_pvs.txt

. .po3_va/bin/activate
virtual_accelerator &
cd .github/workflows || exit
python connection_test.py
