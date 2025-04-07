@Leaksscript(
    name="Slash Command Scheduler V1.2", #bug fix where it would run a cmd twice bc connection drops
    author="Boredom", #Nes for making it work ty
    description="Schedule automatic slash commands with configurable delays",
    usage="""<p>cmdadd <bot_id> <command> <delay_minutes> [args...]
<p>cmdstatus - View all active scheduled commands
<p>cmdstop [id] - Stop a specific command or all commands
<p>cmdstats - View usage statistics"""
)
def slash_command_scheduler():
    import json
    import time
    import asyncio
    from datetime import datetime
    from pathlib import Path
    
    # --- Setup storage paths ---
    BASE_DIR = Path(getScriptsPath()) / "json"
    COMMANDS_FILE = BASE_DIR / "scheduled_commands.json"
    STATS_FILE = BASE_DIR / "command_stats.json"
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    
    # --- Initialize files if they don't exist ---
    if not COMMANDS_FILE.exists():
        with open(COMMANDS_FILE, "w") as f:
            json.dump([], f, indent=4)
    
    if not STATS_FILE.exists():
        with open(STATS_FILE, "w") as f:
            json.dump({
                "total_commands_sent": 0,
                "start_time": time.time()
            }, f, indent=4)
    
    # --- Helper functions ---
    def load_commands():
        try:
            with open(COMMANDS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def save_commands(commands):
        with open(COMMANDS_FILE, "w") as f:
            json.dump(commands, f, indent=4)
    
    def load_stats():
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            stats = {"total_commands_sent": 0, "start_time": time.time()}
            save_stats(stats)
            return stats
    
    def save_stats(stats):
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=4)
    
    def update_command_count():
        stats = load_stats()
        stats["total_commands_sent"] += 1
        save_stats(stats)
    
    # Helper to auto-delete messages after a delay
    async def send_temp_message(ctx, content, delete_after=5):
        msg = await ctx.send(content)
        try:
            await asyncio.sleep(delete_after)
            await msg.delete()
        except:
            pass  # Ignore errors if message already deleted
    
    # --- Command for scheduling slash commands ---
    @bot.command(name="cmdadd", description="Schedule a slash command to run repeatedly")
    async def schedule_slash_command(ctx, *, args: str):
        await ctx.message.delete()
        
        # Parse arguments
        args_parts = args.split()
        if len(args_parts) < 3:
            await send_temp_message(ctx, "Usage: `<p>cmdadd <bot_id> <command> <delay_minutes> [args...]`")
            return
        
        try:
            bot_id = int(args_parts[0])
            command_name = args_parts[1]
            delay_minutes = float(args_parts[2])
            
            # Join remaining args if any
            command_args = {}
            for arg in args_parts[3:]:
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    command_args[key] = value
        except ValueError:
            await send_temp_message(ctx, "Error: Bot ID must be a number and delay must be a number in minutes")
            return
        
        # Create command entry with uniqueness check
        base_command_id = str(int(time.time()))
        command_id = base_command_id
        
        # Check if ID already exists (unlikely but possible)
        commands = load_commands()
        existing_ids = [cmd["id"] for cmd in commands]
        
        # Add a suffix if needed to ensure uniqueness
        suffix = 0
        while command_id in existing_ids:
            suffix += 1
            command_id = f"{base_command_id}_{suffix}"
        command_entry = {
            "id": command_id,
            "bot_id": bot_id,
            "command_name": command_name,
            "delay_minutes": delay_minutes,
            "args": command_args,
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "guild_name": ctx.guild.name if ctx.guild else "DM",
            "start_time": time.time(),
            "next_run": time.time(),
            "times_run": 0,
            "active": True
        }
        
        # Save to commands list
        commands = load_commands()
        commands.append(command_entry)
        save_commands(commands)
        
        await send_temp_message(ctx, f"Scheduled slash command `/{command_name}` to run every {delay_minutes} minutes. ID: `{command_id}`")
        
        # Start the command loop if it's not already running
        ensure_command_loop.start()
    
    # --- Command to check status of scheduled commands ---
    @bot.command(name="cmdstatus", description="Check status of scheduled commands")
    async def check_status(ctx):
        await ctx.message.delete()
        
        commands = load_commands()
        active_commands = [cmd for cmd in commands if cmd.get("active", True)]
        
        if not active_commands:
            await send_temp_message(ctx, "No active scheduled commands.")
            return
        
        current_time = time.time()
        status_message = "**Active Scheduled Commands:**\n"
        
        for cmd in active_commands:
            next_run_in = max(0, cmd["next_run"] - current_time)
            next_run_mins = int(next_run_in // 60)
            next_run_secs = int(next_run_in % 60)
            
            status_message += f"• ID: `{cmd['id']}` - `/{cmd['command_name']}` in {cmd['guild_name']}\n"
            status_message += f"  Next run: {next_run_mins}m {next_run_secs}s | Run count: {cmd['times_run']}\n"
        
        await send_temp_message(ctx, status_message, delete_after=10)  # Longer timeout for status message
    
    # --- Command to stop scheduled commands ---
    @bot.command(name="cmdstop", description="Stop a specific command or all commands")
    async def stop_command(ctx, *, args: str = ""):
        await ctx.message.delete()
        
        command_id = args.strip()
        commands = load_commands()
        
        if not command_id:
            # Stop all commands
            for cmd in commands:
                cmd["active"] = False
            save_commands(commands)
            await send_temp_message(ctx, "Stopped all scheduled commands.")
            return
        
        # Stop specific command
        command_found = False
        for cmd in commands:
            if cmd["id"] == command_id:
                cmd["active"] = False
                command_found = True
                break
        
        if command_found:
            save_commands(commands)
            await send_temp_message(ctx, f"Stopped command with ID: `{command_id}`")
        else:
            await send_temp_message(ctx, f"No command found with ID: `{command_id}`")
    
    # --- Command to show statistics ---
    @bot.command(name="cmdstats", description="Show slash command statistics")
    async def show_stats(ctx):
        await ctx.message.delete()
        
        stats = load_stats()
        commands = load_commands()
        active_commands = [cmd for cmd in commands if cmd.get("active", True)]
        
        # Calculate uptime
        uptime_seconds = time.time() - stats["start_time"]
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        stats_message = "**Slash Command Scheduler Stats:**\n"
        stats_message += f"• Active commands: {len(active_commands)}\n"
        stats_message += f"• Total commands sent: {stats['total_commands_sent']}\n"
        stats_message += f"• Uptime: {days}d {hours}h {minutes}m\n"
        
        # Add active channels/servers
        if active_commands:
            active_channels = set()
            active_servers = set()
            
            for cmd in active_commands:
                active_channels.add(cmd["channel_id"])
                if cmd["guild_id"]:
                    active_servers.add(cmd["guild_id"])
            
            stats_message += f"• Active in {len(active_channels)} channels across {len(active_servers)} servers\n"
        
        await send_temp_message(ctx, stats_message)
    
    # --- Background task to run commands ---
    class CommandLoop:
        def __init__(self):
            self.running = False
            self.task = None
        
        def start(self):
            if not self.running:
                self.running = True
                self.task = asyncio.create_task(self.run_loop())
                print("Command loop started", type_="DEBUG")
            else:
                print("Command loop already running, not starting another", type_="DEBUG")
        
        async def run_loop(self):
            try:
                print("Command loop started running", type_="DEBUG")
                # Add a timestamp to track each loop iteration for debugging
                last_iteration = time.time()
                
                while True:
                    current_time = time.time()
                    iteration_time = current_time - last_iteration
                    last_iteration = current_time
                    
                    # If an iteration is taking unusually long, log it
                    if iteration_time > 10:
                        print(f"Warning: Command loop iteration took {iteration_time:.2f} seconds", type_="WARNING")
                        
                    commands = load_commands()
                    active_commands = [cmd for cmd in commands if cmd.get("active", True)]
                    
                    # Track if any commands were executed
                    commands_updated = False
                    
                    for active_cmd in active_commands:
                        if current_time >= active_cmd["next_run"]:
                            # Time to execute the command
                            try:
                                # Find the command in the full commands list by ID
                                cmd_id = active_cmd["id"]
                                cmd_index = None
                                for i, cmd in enumerate(commands):
                                    if cmd["id"] == cmd_id:
                                        cmd_index = i
                                        break
                                
                                if cmd_index is None:
                                    print(f"Command with ID {cmd_id} not found in full command list", type_="ERROR")
                                    continue
                                
                                # Check if we're within 2 seconds of the last execution to prevent double-runs
                                last_run_time = current_time - active_cmd["next_run"] + (active_cmd["delay_minutes"] * 60)
                                if last_run_time < 2:  # Less than 2 seconds since theoretical last run
                                    print(f"Skipping command {cmd_id} - appears to be a double execution attempt", type_="WARNING")
                                    commands[cmd_index]["next_run"] = current_time + (active_cmd["delay_minutes"] * 60)
                                    commands_updated = True
                                    continue
                                
                                channel = await bot.fetch_channel(active_cmd["channel_id"])
                                # Ensure bot_id is an integer by truncating any decimal part
                                bot_id = int(float(active_cmd["bot_id"]))
                                slash_cmd = await fetchSlashCommand(channel, bot_id, active_cmd["command_name"])
                                
                                # Execute the command with args
                                await execSlashCommand(channel, slash_cmd, **active_cmd["args"])
                                
                                # Update command data in the full commands list
                                commands[cmd_index]["times_run"] += 1
                                commands[cmd_index]["next_run"] = current_time + (active_cmd["delay_minutes"] * 60)
                                update_command_count()
                                commands_updated = True
                                
                                print(f"Executed scheduled command: /{active_cmd['command_name']}", type_="DEBUG")
                            except Exception as e:
                                # Still update the next_run time on failure to prevent immediate retries
                                commands[cmd_index]["next_run"] = current_time + (active_cmd["delay_minutes"] * 60)
                                commands_updated = True
                                print(f"Error executing command {active_cmd['id']}: {str(e)} - Will retry at next scheduled time", type_="ERROR")
                    
                    # Save updated commands only if changes were made
                    if commands_updated:
                        save_commands(commands)
                    
                    # Sleep for a bit to avoid high CPU usage
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"Command loop error: {str(e)}", type_="ERROR")
                self.running = False
    
    # Create instance of command loop
    ensure_command_loop = CommandLoop()
    
    # Initialize the command loop when the bot is ready (has an event loop)
    @bot.listen('on_ready')
    async def initialize_command_loop():
        try:
            # Check if we already have started the command loop
            if ensure_command_loop.running:
                print("Command loop already running, skipping initialization", type_="DEBUG")
                return
                
            # Check for commands that should run immediately
            commands = load_commands()
            if any(cmd.get("active", True) for cmd in commands):
                ensure_command_loop.start()
                print("Command loop started successfully", type_="DEBUG")
        except Exception as e:
            print(f"Error initializing command loop: {str(e)}", type_="ERROR")
    
    print("Slash Command Scheduler initialized", type_="DEBUG")
slash_command_scheduler()