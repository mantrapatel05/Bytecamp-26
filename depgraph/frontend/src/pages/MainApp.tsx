import { motion } from 'framer-motion';
import { AppProvider } from '@/context/AppContext';
import TopBar from '@/components/app/TopBar';
import LeftSidebar from '@/components/app/LeftSidebar';
import GraphCanvas from '@/components/app/GraphCanvas';
import RightPanel from '@/components/app/RightPanel';
import Terminal from '@/components/app/Terminal';

const ease = [0.22, 1, 0.36, 1];

const MainApp = () => {
  return (
    <div className="h-screen flex flex-col overflow-hidden" style={{ background: 'var(--void-hex)' }}>
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <motion.div
          initial={{ opacity: 0, filter: 'blur(8px)', x: -16 }}
          animate={{ opacity: 1, filter: 'blur(0px)', x: 0 }}
          transition={{ duration: 0.5, ease }}
          className="h-full flex flex-col"
        >
          <LeftSidebar />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, filter: 'blur(8px)', y: 8 }}
          animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease }}
          className="flex-1 h-full flex flex-col overflow-hidden"
        >
          <GraphCanvas />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, filter: 'blur(8px)', x: 16 }}
          animate={{ opacity: 1, filter: 'blur(0px)', x: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease }}
          className="h-full flex flex-col"
        >
          <RightPanel />
        </motion.div>
      </div>
      <motion.div
        initial={{ opacity: 0, filter: 'blur(8px)', y: 16 }}
        animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
        transition={{ duration: 0.5, delay: 0.24, ease }}
      >
        <Terminal />
      </motion.div>
    </div>
  );
};

export default MainApp;
