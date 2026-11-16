import {
  LuActivity,
  LuArrowLeft,
  LuArrowLeftRight,
  LuArrowRight,
  LuAudioLines,
  LuAudioWaveform,
  LuBot,
  LuBoxes,
  LuBraces,
  LuChartColumn,
  LuCheck,
  LuChevronDown,
  LuChevronLeft,
  LuChevronRight,
  LuChevronUp,
  LuCircleCheck,
  LuClock,
  LuCopy,
  LuCpu,
  LuDatabase,
  LuExternalLink,
  LuEye,
  LuFileText,
  LuGauge,
  LuGlobe,
  LuHeadset,
  LuHistory,
  LuInbox,
  LuInfo,
  LuKeyRound,
  LuLayers,
  LuLayoutDashboard,
  LuLink,
  LuLoader,
  LuLock,
  LuLogOut,
  LuMail,
  LuMenu,
  LuMessagesSquare,
  LuMic,
  LuMicOff,
  LuPause,
  LuPencil,
  LuPhoneCall,
  LuPhoneOff,
  LuPhoneOutgoing,
  LuPlay,
  LuPlug,
  LuPlus,
  LuPower,
  LuRefreshCw,
  LuSearch,
  LuServer,
  LuSettings,
  LuShieldCheck,
  LuSlidersHorizontal,
  LuSmartphone,
  LuSparkles,
  LuSquareTerminal,
  LuSun,
  LuMoon,
  LuTimer,
  LuTrash2,
  LuTriangleAlert,
  LuUnplug,
  LuUsers,
  LuBuilding2,
  LuWorkflow,
  LuWrench,
  LuX,
  LuZap,
} from "react-icons/lu";

const STROKE = 1.9;

const icon = (Component) => {
  const Icon = ({ size = 17, ...rest }) => <Component size={size} strokeWidth={STROKE} aria-hidden="true" {...rest} />;
  Icon.displayName = Component.displayName || Component.name;
  return Icon;
};

export const Gauge = icon(LuGauge);
export const Waves = icon(LuAudioWaveform);
export const Sliders = icon(LuSlidersHorizontal);
export const PhoneOut = icon(LuPhoneOutgoing);
export const PhoneCall = icon(LuPhoneCall);
export const Terminal = icon(LuSquareTerminal);
export const Users = icon(LuUsers);
export const Building = icon(LuBuilding2);
export const Hangup = icon(LuPhoneOff);
export const Refresh = icon(LuRefreshCw);
export const Power = icon(LuPower);
export const Sun = icon(LuSun);
export const Moon = icon(LuMoon);
export const Check = icon(LuCheck);
export const CheckCircle = icon(LuCircleCheck);
export const X = icon(LuX);
export const Alert = icon(LuTriangleAlert);
export const Info = icon(LuInfo);
export const Search = icon(LuSearch);
export const Menu = icon(LuMenu);
export const Database = icon(LuDatabase);
export const FileText = icon(LuFileText);
export const Copy = icon(LuCopy);
export const Pause = icon(LuPause);
export const Play = icon(LuPlay);
export const Eye = icon(LuEye);
export const Key = icon(LuKeyRound);
export const Activity = icon(LuActivity);
export const Globe = icon(LuGlobe);
export const Plug = icon(LuPlug);
export const Unplug = icon(LuUnplug);
export const Transfer = icon(LuArrowLeftRight);
export const Plus = icon(LuPlus);
export const Trash = icon(LuTrash2);
export const Pencil = icon(LuPencil);
export const Inbox = icon(LuInbox);
export const Bot = icon(LuBot);
export const Wrench = icon(LuWrench);
export const Shield = icon(LuShieldCheck);
export const Gear = icon(LuSettings);
export const Lock = icon(LuLock);
export const LogOut = icon(LuLogOut);
export const Mail = icon(LuMail);
export const Sparkle = icon(LuSparkles);
export const ArrowLeft = icon(LuArrowLeft);
export const ArrowRight = icon(LuArrowRight);
export const History = icon(LuHistory);
export const Mic2 = icon(LuAudioLines);
export const Layers = icon(LuLayers);
export const Braces = icon(LuBraces);
export const Server = icon(LuServer);
export const Dashboard = icon(LuLayoutDashboard);
export const Flow = icon(LuWorkflow);
export const Clock = icon(LuClock);
export const Timer = icon(LuTimer);
export const Chat = icon(LuMessagesSquare);
export const Cpu = icon(LuCpu);
export const Zap = icon(LuZap);
export const Boxes = icon(LuBoxes);
export const Chart = icon(LuChartColumn);
export const Headset = icon(LuHeadset);
export const Link2 = icon(LuLink);
export const External = icon(LuExternalLink);
export const Phone = icon(LuSmartphone);
export const Spinner = icon(LuLoader);

export const Mic = ({ size = 17, off = false, ...rest }) =>
  off ? <LuMicOff size={size} strokeWidth={STROKE} aria-hidden="true" {...rest} /> : <LuMic size={size} strokeWidth={STROKE} aria-hidden="true" {...rest} />;

const CHEVRONS = { down: LuChevronDown, up: LuChevronUp, left: LuChevronLeft, right: LuChevronRight };
export const Chevron = ({ size = 17, dir = "down", ...rest }) => {
  const Component = CHEVRONS[dir] || LuChevronDown;
  return <Component size={size} strokeWidth={STROKE} aria-hidden="true" {...rest} />;
};
