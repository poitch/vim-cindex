" This is basic vim plugin boilerplate
let s:save_cpo = &cpo
set cpo&vim

function! s:restore_cpo()
    let &cpo = s:save_cpo
    unlet s:save_cpo
endfunction

if exists( "g:loaded_cindex" )
    call s:restore_cpo()
    finish
elseif !has( 'python' ) && !has( 'python3' )
    echohl WarningMsg |
                \ echomsg "CIndex unavailable: requires Vim compiled with " .
                \ "Python (2.6+ or 3.3+) support" |
                \ echohl None
    call s:restore_cpo()
    finish
endif

let g:loaded_cindex = 1

" On-demand loading. Let's use the autoload folder and not slow down vim's
" startup procedure.
if has( 'vim_starting' ) " loading at startup
    augroup cindexStart
        autocmd!
        autocmd VimEnter * call cindex#Enable()
    augroup END
else " manual loading with :packadd
    call cindex#Enable()
endif

" This is basic vim plugin boilerplate
call s:restore_cpo()
"
