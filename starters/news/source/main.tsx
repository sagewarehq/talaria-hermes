import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import App from './App'
import './style.css'

createRoot(document.getElementById('app')!).render(<MotionConfig reducedMotion="user"><App /></MotionConfig>)
