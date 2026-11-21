"""Import Windows AIWorkstation.Core WorkTask JSON as NON-EXECUTABLE guest history.

Windows WorkflowStep/UnifiedTaskState data is not an authority to execute
Linux tools. All imported stages remain 'unmapped': original status,
plan-revision and artifact evidence are retained as bounded metadata only.
Instructions, token logs, prompts and result contents are never persisted.
"""
import hashlib
import json
import re

GUID=re.compile(r"^[0-9a-fA-F]{32}$")
HEX=re.compile(r"^[0-9a-fA-F]{64}$")
STATUSES=frozenset({"Pending","Running","Completed","Failed","Interrupted"})
AGENTS=frozenset({"ClaudeCode","Codex","Manual"})
MAX_IMPORT_STAGES=32

class WindowsImportError(ValueError):
    pass

def digest(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),ensure_ascii=False
    ).encode("utf-8")).hexdigest()

def guid(value,field):
    if not isinstance(value,str) or not GUID.fullmatch(value):
        raise WindowsImportError("Invalid Windows "+field+" GUID")
    return value.lower()

def text(value,name,maxsize,empty=False):
    if not isinstance(value,str) or len(value)>maxsize or (not empty and not value.strip()):
        raise WindowsImportError("Invalid bounded Windows "+name)
    return value

def summarize_unified(unified):
    if unified is None:
        unified={}
    if not isinstance(unified,dict) or unified.get("SchemaVersion",1)!=1:
        raise WindowsImportError("Unsupported Windows UnifiedTaskState schema")
    plans=unified.get("Plans",[]) or []
    artifacts=unified.get("Artifacts",[]) or []
    runs=unified.get("AgentRuns",[]) or []
    if not isinstance(plans,list) or len(plans)>80 or not isinstance(artifacts,list) or len(artifacts)>500 or not isinstance(runs,list) or len(runs)>500:
        raise WindowsImportError("Unbounded Windows evidence collection")
    hashes=[]
    for item in plans:
        if not isinstance(item,dict):
            raise WindowsImportError("Invalid Windows plan revision")
        value=item.get("Sha256")
        if not isinstance(value,str) or not HEX.fullmatch(value):
            raise WindowsImportError("Windows plan revision is missing SHA256")
        hashes.append(value.lower())
    refs=[]
    for item in artifacts:
        if not isinstance(item,dict) or item.get("Kind") not in ("plan","stage-result"):
            raise WindowsImportError("Invalid Windows artifact")
        value=item.get("ContentHash")
        if not isinstance(value,str) or not HEX.fullmatch(value):
            raise WindowsImportError("Windows artifact hash missing")
        refs.append({"kind":item["Kind"],"sha256":value.lower()})
    run_summaries=[]
    for item in runs:
        if not isinstance(item,dict):
            raise WindowsImportError("Invalid Windows AgentRunRecord")
        agent=item.get("Agent")
        status=item.get("Status")
        if agent not in AGENTS or status not in STATUSES:
            raise WindowsImportError("Unrecognized Windows AgentRunRecord enum")
        run_summaries.append({
            "id":guid(item.get("Id"),"agent run"),
            "agent":agent,"status":status,
            "stageId":guid(item.get("StageId"),"run stage"),
        })
    return {"planRevisionSha256":hashes,"artifactRefs":refs,"agentRuns":run_summaries}

def convert_windows_task(data):
    if not isinstance(data,dict):
        raise WindowsImportError("Windows WorkTask object expected")
    task_id=guid(data.get("Id"),"task")
    title=text(data.get("Title"),"title",160)
    graph=data.get("GraphMode",False)
    if not isinstance(graph,bool):
        raise WindowsImportError("Windows GraphMode must be boolean")
    steps=data.get("Steps")
    if not isinstance(steps,list) or not (1<=len(steps)<=MAX_IMPORT_STAGES):
        raise WindowsImportError("Windows import supports 1-32 workflow stages")
    unified=data.get("Unified") or {}
    metadata=summarize_unified(unified)
    goal=text(unified.get("Goal") or title,"goal",4000)
    executions=data.get("ExecutionRecords",[]) or []
    if not isinstance(executions,list) or len(executions)>2000:
        raise WindowsImportError("Invalid bounded Windows execution ledger")
    metadata["originalExecutionRecordCount"]=len(executions)
    metadata["graphMode"]=graph
    converted=[]
    ids=set()
    for i,entry in enumerate(steps):
        if not isinstance(entry,dict):
            raise WindowsImportError("Windows WorkflowStep object expected")
        stage_id=guid(entry.get("Id"),"step")
        if stage_id in ids:
            raise WindowsImportError("Duplicate Windows step ID")
        ids.add(stage_id)
        label=text(entry.get("Title"),"step title",160)
        status=entry.get("Status","Pending")
        agent=entry.get("Agent","Manual")
        if status not in STATUSES or agent not in AGENTS:
            raise WindowsImportError("Unknown Windows Agent or StepStatus")
        requires=entry.get("RequiresApproval",True)
        granted=entry.get("ApprovalGranted",False)
        if not isinstance(requires,bool) or not isinstance(granted,bool):
            raise WindowsImportError("Windows approval flags must be boolean")
        dep=entry.get("DependsOn",[]) or []
        if not isinstance(dep,list) or len(dep)>MAX_IMPORT_STAGES:
            raise WindowsImportError("Invalid Windows dependencies")
        dep=[guid(x,"dependency") for x in dep]
        if not graph:
            # Windows non-graph workflow is sequential, even when DependsOn=[].
            dep=[] if i==0 else [converted[-1]["key"]]
        result=entry.get("Result","")
        instructions=entry.get("Instructions","")
        if not isinstance(result,str) or not isinstance(instructions,str):
            raise WindowsImportError("Windows result/instructions must be strings")
        converted.append({
            "key":stage_id,"label":label,"dependsOn":dep,
            "windowsStatus":status,"windowsAgent":agent,
            "windowsRequiresApproval":requires,
            "windowsApprovalGranted":granted,
            "resultSha256":hashlib.sha256(result.encode("utf-8")).hexdigest() if result else None,
            "instructionsSha256":hashlib.sha256(instructions.encode("utf-8")).hexdigest() if instructions else None,
        })
    graph_map={x["key"]:x["dependsOn"] for x in converted}
    visited=set()
    def visit(key,active):
        if key in active:
            raise WindowsImportError("Windows DAG cycle")
        if key in visited:
            return
        for predecessor in graph_map[key]:
            if predecessor not in graph_map or predecessor==key:
                raise WindowsImportError("Unknown or self-referential Windows dependency")
            visit(predecessor,active|{key})
        visited.add(key)
    for key in graph_map:
        visit(key,set())
    metadata["stages"]=[{
        k:s[k] for k in ("key","windowsStatus","windowsAgent",
                        "windowsRequiresApproval","windowsApprovalGranted",
                        "resultSha256","instructionsSha256")
    } for s in converted]
    metadata["sourceSha256"]=digest(data)
    return {"taskId":task_id,"title":title,"goal":goal,"stages":converted,
            "metadata":metadata}
