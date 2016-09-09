" Description: Index C and C++ files
" Author: Jerome Poichet <poitch@gmail.com>
" License: MIT

if exists('loaded_jpo') || &compatible || v:version < 700
    finish
endif
let loaded_jpo = 1
let s:script_folder_path = escape( expand( '<sfile>:p:h' ), '\' )
echom s:script_folder_path
let s:indexer_command = s:script_folder_path . "search"

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
		exec ":bwipeout " l:bufn

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
sys.path.insert( 0, os.path.join( script_folder, '..', 'python' ) )
try:
    from cindex import server
    vim.command( "echom 'Hello'" )
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
endfunction


