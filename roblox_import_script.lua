--[[
    Pet Model Importer for Roblox Studio
    
    This script reads the JSON metadata exported from the Blender Pet Optimizer addon
    and creates Motor6D joints between imported mesh parts.
    
    Usage:
    1. Import your FBX/OBJ pet model parts into Roblox Studio
    2. Place them under a Model in Workspace
    3. Copy this script into a Script in ServerScriptService
    4. Update the METADATA_PATH to point to your JSON file
    5. Run the script
]]

local HttpService = game:GetService("HttpService")

local CONFIG = {
    METADATA_PATH = "path/to/your/pet_r6_metadata.json",
    MODEL_NAME = "PetModel",
    ROOT_PART_NAME = "Body",
    CREATE_WELDS = true,
    DEBUG_MODE = true,
}

local function log(message)
    if CONFIG.DEBUG_MODE then
        print("[PetImporter] " .. message)
    end
end

local function matrixToCFrame(matrix)
    if not matrix or #matrix < 4 then
        return CFrame.new()
    end
    
    local m = matrix
    return CFrame.new(
        m[1][4], m[2][4], m[3][4],
        m[1][1], m[1][2], m[1][3],
        m[2][1], m[2][2], m[2][3],
        m[3][1], m[3][2], m[3][3]
    )
end

local function positionRotationToCFrame(position, rotation)
    if not position then
        return CFrame.new()
    end
    
    local pos = CFrame.new(position[1] or 0, position[2] or 0, position[3] or 0)
    
    if rotation then
        local rx = math.rad(rotation[1] or 0)
        local ry = math.rad(rotation[2] or 0)
        local rz = math.rad(rotation[3] or 0)
        local rot = CFrame.Angles(rx, ry, rz)
        return pos * rot
    end
    
    return pos
end

local function getCFrameFromJointData(jointData, useMatrix)
    if useMatrix and jointData.matrix then
        return matrixToCFrame(jointData.matrix)
    elseif jointData.position then
        return positionRotationToCFrame(jointData.position, jointData.rotation)
    end
    return CFrame.new()
end

local function findPart(model, partName)
    local part = model:FindFirstChild(partName)
    if part then
        return part
    end
    
    for _, child in ipairs(model:GetDescendants()) do
        if child.Name:lower():find(partName:lower()) then
            return child
        end
    end
    
    return nil
end

local function createMotor6D(parent, name, part0, part1, c0, c1)
    local motor = Instance.new("Motor6D")
    motor.Name = name
    motor.Part0 = part0
    motor.Part1 = part1
    motor.C0 = c0
    motor.C1 = c1
    motor.Parent = parent
    
    log(string.format("Created Motor6D '%s': %s -> %s", name, part0.Name, part1.Name))
    
    return motor
end

local function createWeld(parent, name, part0, part1, c0)
    local weld = Instance.new("Weld")
    weld.Name = name
    weld.Part0 = part0
    weld.Part1 = part1
    weld.C0 = c0
    weld.Parent = parent
    
    log(string.format("Created Weld '%s': %s -> %s", name, part0.Name, part1.Name))
    
    return weld
end

local function processJoints(model, jointsData, useMatrix)
    local createdJoints = 0
    local failedJoints = {}
    
    for _, joint in ipairs(jointsData) do
        local part0 = findPart(model, joint.part0)
        local part1 = findPart(model, joint.part1)
        
        if part0 and part1 then
            local c0 = getCFrameFromJointData(joint.c0, useMatrix)
            local c1 = getCFrameFromJointData(joint.c1, useMatrix)
            
            if joint.type == "Motor6D" then
                createMotor6D(part0, joint.name, part0, part1, c0, c1)
            else
                createWeld(part0, joint.name, part0, part1, c0)
            end
            
            createdJoints = createdJoints + 1
        else
            local missing = {}
            if not part0 then table.insert(missing, joint.part0) end
            if not part1 then table.insert(missing, joint.part1) end
            table.insert(failedJoints, {
                name = joint.name,
                missing = missing
            })
            log(string.format("WARNING: Could not find parts for joint '%s': %s", 
                joint.name, table.concat(missing, ", ")))
        end
    end
    
    return createdJoints, failedJoints
end

local function setRootPart(model)
    local rootPart = findPart(model, CONFIG.ROOT_PART_NAME)
    if rootPart and rootPart:IsA("BasePart") then
        model.PrimaryPart = rootPart
        log("Set PrimaryPart to: " .. rootPart.Name)
        return true
    end
    return false
end

local function anchorModel(model, anchored)
    for _, part in ipairs(model:GetDescendants()) do
        if part:IsA("BasePart") then
            part.Anchored = anchored
        end
    end
    log("Set all parts Anchored = " .. tostring(anchored))
end

local function importFromMetadata(metadataJson)
    local success, metadata = pcall(function()
        return HttpService:JSONDecode(metadataJson)
    end)
    
    if not success then
        warn("[PetImporter] Failed to parse JSON metadata: " .. tostring(metadata))
        return false
    end
    
    local model = workspace:FindFirstChild(CONFIG.MODEL_NAME)
    if not model then
        warn("[PetImporter] Could not find model '" .. CONFIG.MODEL_NAME .. "' in Workspace")
        return false
    end
    
    log("Found model: " .. model.Name)
    log("Processing " .. #(metadata.joints or {}) .. " joints...")
    
    local useMatrix = true
    local createdJoints, failedJoints = processJoints(model, metadata.joints or {}, useMatrix)
    
    setRootPart(model)
    
    log("=== Import Complete ===")
    log(string.format("Created %d joints", createdJoints))
    
    if #failedJoints > 0 then
        warn("[PetImporter] Failed to create " .. #failedJoints .. " joints:")
        for _, failed in ipairs(failedJoints) do
            warn("  - " .. failed.name .. " (missing: " .. table.concat(failed.missing, ", ") .. ")")
        end
    end
    
    return true
end

local function importFromModuleScript(moduleScriptName)
    log("=== Pet Model Importer ===")
    log("Looking for model: " .. CONFIG.MODEL_NAME)
    
    local metadataModule = game:GetService("ReplicatedStorage"):FindFirstChild(moduleScriptName)
    if not metadataModule then
        metadataModule = game:GetService("ServerStorage"):FindFirstChild(moduleScriptName)
    end
    
    if metadataModule and metadataModule:IsA("ModuleScript") then
        local success, jsonData = pcall(function()
            return require(metadataModule)
        end)
        
        if success and type(jsonData) == "string" then
            log("Loaded metadata from ModuleScript: " .. moduleScriptName)
            return importFromMetadata(jsonData)
        elseif success and type(jsonData) == "table" then
            log("Loaded metadata table from ModuleScript: " .. moduleScriptName)
            local jsonString = HttpService:JSONEncode(jsonData)
            return importFromMetadata(jsonString)
        else
            warn("[PetImporter] Failed to load ModuleScript: " .. tostring(jsonData))
            return false
        end
    end
    
    warn("[PetImporter] ModuleScript not found: " .. moduleScriptName)
    warn("[PetImporter] Create a ModuleScript in ReplicatedStorage or ServerStorage with your JSON metadata")
    return false
end

local function importFromStringValue(stringValueName)
    log("=== Pet Model Importer ===")
    log("Looking for StringValue: " .. stringValueName)
    
    local stringValue = game:GetService("ReplicatedStorage"):FindFirstChild(stringValueName)
    if not stringValue then
        stringValue = game:GetService("ServerStorage"):FindFirstChild(stringValueName)
    end
    
    if stringValue and stringValue:IsA("StringValue") then
        log("Loaded metadata from StringValue: " .. stringValueName)
        return importFromMetadata(stringValue.Value)
    end
    
    warn("[PetImporter] StringValue not found: " .. stringValueName)
    return false
end

local function createImportModule()
    local module = {}
    
    function module.importFromJson(jsonString, modelName)
        if modelName then
            CONFIG.MODEL_NAME = modelName
        end
        return importFromMetadata(jsonString)
    end
    
    function module.importFromModule(moduleScriptName, modelName)
        if modelName then
            CONFIG.MODEL_NAME = modelName
        end
        return importFromModuleScript(moduleScriptName or "PetMetadata")
    end
    
    function module.importFromStringValue(stringValueName, modelName)
        if modelName then
            CONFIG.MODEL_NAME = modelName
        end
        return importFromStringValue(stringValueName or "PetMetadataJSON")
    end
    
    function module.setConfig(config)
        for key, value in pairs(config) do
            CONFIG[key] = value
        end
    end
    
    function module.createJointManually(model, jointName, part0Name, part1Name, c0, c1)
        local part0 = findPart(model, part0Name)
        local part1 = findPart(model, part1Name)
        
        if part0 and part1 then
            return createMotor6D(part0, jointName, part0, part1, c0 or CFrame.new(), c1 or CFrame.new())
        end
        
        return nil
    end
    
    return module
end

return createImportModule()
