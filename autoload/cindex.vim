let s:script_folder_path = escape( expand( '<sfile>:p:h' ), '\' )
let s:indexer_command = s:script_folder_path . "/../python/cindex/search.py"

" Call to initialize vim.cindex plugin
function! cindex#Enable()
    if s:SetupPython() != 1
        return
    endif

    call s:SetupKeyMappings()
    call s:SetupCommands()

    " Automatically start server and index current working directory
    if g:cindex_autostart
      call cindex#StartServer()
      call cindex#Reindex()
    endif
endfunction

" Starts vim.cindex server and retrieve assigned port
function! cindex#StartServer()
python << endpython
import vim
port = cindexer.StartServer()
vim.command("let s:cindex_port = {0}".format(port))
endpython
endfunction

function! cindex#SendMessage(msg)
  "echom "system " . s:indexer_command . " --port " . s:cindex_port ." " . a:msg
  return system(s:indexer_command . " --port " . s:cindex_port . " " . a:msg)
endfunction

" Stops vim.cindex server
function! cindex#StopServer()
  call system(s:indexer_command . " --port " . s:cindex_port . " QUIT ")
endfunction

" Reindex files within current directory
function! cindex#Reindex()
    let curDir = getcwd()
    call cindex#SendMessage("INDEX " . curDir)
endfunction

function! cindex#JumpToImplementation()
  let wordUnderCursor = expand("<cword>")
  "silent !clear
  let location = cindex#SendMessage("IMPL " . wordUnderCursor)
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

function! cindex#Calls()
  let wordUnderCursor = expand("<cword>")
  let calls = cindex#SendMessage("CALLS " . wordUnderCursor)

  let mylist = split(calls, '\v\n')
  cgetexpr mylist
  botright copen 5
  " Auto-close
  let l:closemap = ':cclose<CR>'
  execute "nnoremap <buffer> <silent> <CR> <CR>" . l:closemap

endfunction

function s:SetupPython()
python << endpython
import os
import traceback
import vim
# Add python sources folder to the system path.
debug_server = vim.eval('g:cindex_debug_server')
script_folder = vim.eval( 's:script_folder_path' )
include_folder = os.path.join( script_folder, '..', 'python' )
sys.path.insert( 0, include_folder )
try:
    from cindex.setup import SetupCIndex
    cindexer = SetupCIndex(debug_server)
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
    nnoremap <C-C> :call cindex#Calls()<cr>
endfunction

function s:SetupCommands()
    command! CIJumpToImplementation call cindex#JumpToImplementation()
    command! CIStartServer call cindex#StartServer()
    command! CIStopServer call cindex#StopServer()
    command! CIIndex call cindex#Reindex()
    command! CICalls call cindex#Calls()
endfunction

