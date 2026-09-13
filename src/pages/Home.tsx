import { motion } from 'framer-motion';
import { Hop as HomeIcon, Search, CirclePlus as PlusCircle, MessageCircle, User, LogOut } from 'lucide-react';
import { cn } from '@/utils/cn';
import { apiJson } from '@/utils/socialApi';

interface HomeProps {
  user?: {
    username: string;
    email?: string;
  };
  onNavigate: (page: string) => void;
}

export function Home({ user, onNavigate }: HomeProps) {
  const handleLogout = async () => {
    try {
      await apiJson('/api/auth/logout', { method: 'POST' });
    } catch {
      // Local session cleanup still happens if the remote session is already invalid.
    } finally {
      localStorage.removeItem('user');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      onNavigate('login');
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#0B0C10] pb-24">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#0F1015]/90 backdrop-blur-xl border-b border-white/10">
        <div className="px-4 py-3 flex items-center justify-between">
          <h1 className="text-xl font-light tracking-[0.2em] text-white font-['Share_Tech_Mono',monospace]">
            SHADOW
          </h1>
          <div className="flex items-center gap-3">
            <span className="px-3 py-1 rounded-full bg-pink-500/20 text-pink-400 text-[10px] font-mono tracking-wider border border-pink-500/30">
              LIVE
            </span>
            <button
              onClick={() => void handleLogout()}
              className="text-white/40 hover:text-white/80 transition-colors"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="px-4 py-6 space-y-6">
        {/* User Profile Card */}
        <div className="bg-[#0F1015]/60 backdrop-blur-xl border border-pink-500/30 rounded-2xl p-6 shadow-[0_0_15px_rgba(236,72,153,0.2)]">
          <div className="flex flex-col items-center text-center">
            {/* Avatar */}
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-pink-500 to-purple-500 flex items-center justify-center text-white text-2xl font-bold mb-4 ring-2 ring-pink-500/50 ring-offset-2 ring-offset-[#0B0C10]">
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </div>

            {/* User Info */}
            <h2 className="text-xl font-medium text-white">
              {user?.username || 'User'}
            </h2>
            <p className="text-sm text-white/40 mt-1">
              {user?.email || 'Welcome to Shadow'}
            </p>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[#0F1015]/60 backdrop-blur-xl border border-white/10 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-pink-400">0</div>
            <div className="text-[10px] text-white/40 uppercase tracking-wider mt-1">Posts</div>
          </div>
          <div className="bg-[#0F1015]/60 backdrop-blur-xl border border-white/10 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-pink-400">0</div>
            <div className="text-[10px] text-white/40 uppercase tracking-wider mt-1">Followers</div>
          </div>
          <div className="bg-[#0F1015]/60 backdrop-blur-xl border border-white/10 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-pink-400">0</div>
            <div className="text-[10px] text-white/40 uppercase tracking-wider mt-1">Following</div>
          </div>
        </div>

        {/* OMNI Score */}
        <div className="bg-[#0F1015]/60 backdrop-blur-xl border border-pink-500/30 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs text-white/40 uppercase tracking-wider">OMNI Score</div>
            <div className="text-2xl font-bold text-pink-400">0.0</div>
          </div>
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <div className="h-full w-0 bg-gradient-to-r from-pink-500 to-purple-500 rounded-full" />
          </div>
        </div>

        {/* Empty Feed State */}
        <div className="bg-[#0F1015]/40 border border-white/10 rounded-2xl p-8 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-pink-500/10 flex items-center justify-center">
            <PlusCircle className="w-8 h-8 text-pink-400" />
          </div>
          <h3 className="text-lg font-medium text-white mb-2">No posts yet</h3>
          <p className="text-sm text-white/40 mb-4">
            Your feed is empty. Create your first post to get started!
          </p>
          <button
            onClick={() => onNavigate('create')}
            className="px-6 py-2 bg-gradient-to-r from-pink-500 to-pink-400 text-white font-semibold text-sm rounded-xl hover:shadow-[0_0_20px_rgba(236,72,153,0.4)] transition-all duration-200"
          >
            Create Post
          </button>
        </div>
      </div>

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 bg-[#0F1015]/95 backdrop-blur-xl border-t border-white/10 z-50">
        <div className="flex items-center justify-around py-3 px-2">
          <NavButton icon={HomeIcon} label="Home" active onClick={() => onNavigate('home')} />
          <NavButton icon={Search} label="Search" onClick={() => onNavigate('search')} />
          <NavButton icon={PlusCircle} label="Create" onClick={() => onNavigate('create')} />
          <NavButton icon={MessageCircle} label="Chat" onClick={() => onNavigate('chat')} />
          <NavButton icon={User} label="Profile" onClick={() => onNavigate('profile')} />
        </div>
      </nav>
    </div>
  );
}

interface NavButtonProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  active?: boolean;
  onClick: () => void;
}

function NavButton({ icon: Icon, label, active, onClick }: NavButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex flex-col items-center gap-1 px-3 py-2 transition-colors',
        active ? 'text-pink-400' : 'text-white/40 hover:text-white/60'
      )}
    >
      <Icon className="w-5 h-5" />
      <span className="text-[10px] font-mono tracking-wider">{label.toUpperCase()}</span>
    </button>
  );
}