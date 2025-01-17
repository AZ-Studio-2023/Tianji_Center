function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    const messageEl = toast.querySelector('.text-sm');
    const iconEl = toast.querySelector('.flex-shrink-0');
    
    // 设置消息
    messageEl.textContent = message;
    
    // 设置样式
    switch(type) {
        case 'success':
            toast.querySelector('.rounded-lg').className = 'flex items-center p-4 mb-4 text-green-800 rounded-lg bg-green-50';
            iconEl.className = 'inline-flex items-center justify-center flex-shrink-0 w-8 h-8 text-green-500 bg-green-100 rounded-lg';
            break;
        case 'error':
            toast.querySelector('.rounded-lg').className = 'flex items-center p-4 mb-4 text-red-800 rounded-lg bg-red-50';
            iconEl.className = 'inline-flex items-center justify-center flex-shrink-0 w-8 h-8 text-red-500 bg-red-100 rounded-lg';
            break;
        case 'warning':
            toast.querySelector('.rounded-lg').className = 'flex items-center p-4 mb-4 text-yellow-800 rounded-lg bg-yellow-50';
            iconEl.className = 'inline-flex items-center justify-center flex-shrink-0 w-8 h-8 text-yellow-500 bg-yellow-100 rounded-lg';
            break;
        default:
            toast.querySelector('.rounded-lg').className = 'flex items-center p-4 mb-4 text-blue-800 rounded-lg bg-blue-50';
            iconEl.className = 'inline-flex items-center justify-center flex-shrink-0 w-8 h-8 text-blue-500 bg-blue-100 rounded-lg';
    }
    
    // 显示提示
    toast.classList.remove('translate-x-full');
    
    // 3秒后自动隐藏
    setTimeout(() => {
        toast.classList.add('translate-x-full');
    }, 3000);
}

// 关闭按钮事件
document.addEventListener('click', function(e) {
    if (e.target.closest('[data-dismiss-target="#toast"]')) {
        document.getElementById('toast').classList.add('translate-x-full');
    }
}); 