$pdf_mode = 5;

# 让 latexmk 在本目录编译时自动找到哈尔滨工程大学模板文件。
# 这样 main.tex 不需要写相对路径加载 cls/sty，LaTeX Workshop 也不会反复报模板路径警告。
$ENV{'TEXINPUTS'} = '../bachelor//;' . ($ENV{'TEXINPUTS'} // '');
