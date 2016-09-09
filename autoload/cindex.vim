" Description: Index C and C++ files
" Author: Jerome Poichet <poitch@gmail.com>
" License: MIT

let s:script_folder_path = escape( expand( '<sfile>:p:h' ), '\' )
let s:indexer_command = s:script_folder_path . "../python/cindex/search.py"

function! cindex#Enable()
    if s:SetupPython() != 1
        return
    endif

    call s:SetupKeyMappings()
    call s:SetupCommands()
endfunction

function! cindex#StartServer()
python << endpython
import vim
port = cindexer.StartServer()
vim.command("let s:cindex_port = {0}".format(port))
vim.command('echom "Port = " . s:cindex_port')
endpython
endfunction

function! cindex#StopServer()
python << endpython
import vim
cindexer.StopServer()
endpython
endfunction

function! cindex#Reindex()
    let curDir = getcwd()
    let location = system(s:indexer_command ." INDEX " . curDir)
endfunction

function! cindex#JumpToImplementation()
    let wordUnderCursor = expand("<cword>")
    silent !clear
    let location = system(s:indexer_command ." IMPL " . wordUnderCursor)
	let names =  matchlist( location, '\(.\{-1,}\):\%(\(\d\+\)\%(:\(\d*\):\?\)\?\)\?')
	if empty(names)
		return
	endif

	let file_name = names[1]
	let line_num  = names[2] == ''? '0' : names[2]
	let  col_num  = names[3] == ''? '0' : names[3]

	if filereadable(file_name)
		let l:bufn = bufnr("%")
        "exec ":bwipeout " l:bufn

		exec "keepalt edit " . file_name
		exec ":" . line_num
		exec "normal! " . col_num . '|'
		if foldlevel(line_num) > 0
			exec "normal! zv"
		endif


		exec "normal! zz"
	endif
endfunction

function s:SetupPython()
python << endpython
import os
import traceback
import vim
# Add python sources folder to the system path.
script_folder = vim.eval( 's:script_folder_path' )
include_folder = os.path.join( script_folder, '..', 'python' )
sys.path.insert( 0, include_folder )
try:
    from cindex.setup import SetupCIndex
    cindexer = SetupCIndex()
except Exception as error:
    vim.command( 'redraw | echohl WarningMsg' )
    for line in traceback.format_exc().splitlines():
        vim.command( "echom '{0}'".format( line.replace( "'", "''" ) ) )

    vim.command( "echo 'CIndex unavailable: {0}'"
                  .format( str( error ).replace( "'", "''" ) ) )
    vim.command( 'echohl None' )
    vim.command( 'return 0' )
else:
    vim.command( 'return 1' )
endpython
endfunction

function s:SetupKeyMappings()
    nnoremap <C-I> :call cindex#JumpToImplementation()<cr>
endfunction

function s:SetupCommands()
    command! CIJumpToImplementation call cindex#JumpToImplementation()
    command! CIRestartServer call cindex#StartServer()
endfunction

