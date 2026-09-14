import { FaPython } from "react-icons/fa"; //task python
import { TbWorldWww } from "react-icons/tb";
import { VscTerminalCmd } from "react-icons/vsc";
import { MdOutlineCallSplit } from "react-icons/md";
import { FaRobot } from "react-icons/fa";
import { BiImport } from "react-icons/bi";

export function PythonIcon() {
    return <FaPython />
}
export function WebIcon() {
    return <TbWorldWww />
}
export function BashIcon() {
    return <VscTerminalCmd />
}
export function SplitIcon() {
    return <MdOutlineCallSplit />
}
export function RobotIcon() {
    return <FaRobot />
}
export function BiImportIcon() {
    return <BiImport />
}

export function getIcon(name: string) {
    switch (name) {
        case 'python':
            return <PythonIcon />
        case 'http_request':
            return <WebIcon />
        case 'shell':
            return <BashIcon />
        case 'condition':
            return <SplitIcon />
        case 'agent_step':
            return <RobotIcon />
        case 'input':
            return <BiImportIcon />
        default:
            return null
    }
}