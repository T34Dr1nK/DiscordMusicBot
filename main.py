import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from collections import deque
from dotenv import load_dotenv
import os

# Set up the bot with the prefix `!`
intents = discord.Intents.default()
intents.message_content = True  # Required for Discord.py v2.x
bot = commands.Bot(command_prefix="!", intents=intents)

'load .env'
load_dotenv()

# Queue to store preloaded song paths and titles
song_queue = deque()
volume = 1.0  # Default volume at 100%

# yt-dlp configuration
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': False,
    'verbose': True
}

# FFmpeg options
def get_ffmpeg_options(volume):
    return {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': f'-vn -ar 48000 -ac 2 -b:a 128k -filter:a "volume={volume}"'
    }

@bot.event
async def on_ready():
    print(f"Bot is ready and logged in as {bot.user}")

@bot.command(name="join", help="Bot joins your current voice channel")
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send("Joined the voice channel.")
    else:
        await ctx.send("You are not in a voice channel!")

@bot.command(name="leave", help="Bot leaves the current voice channel")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel.")
    else:
        await ctx.send("I'm not connected to a voice channel.")

@bot.command(name="volume", help="Adjust the playback volume (0.0 to 2.0)")
async def set_volume(ctx, vol: float):
    global volume
    if 0.0 <= vol <= 2.0:
        volume = vol
        await ctx.send(f"Volume set to {volume * 100}%")
    else:
        await ctx.send("Please enter a volume between 0.0 and 2.0 (where 1.0 is 100%).")

@bot.command(name="play", help="Plays a song from a YouTube URL or adds to the queue")
async def play(ctx, url):
    if not ctx.voice_client:
        await ctx.invoke(join)

    await ctx.send(f"Adding to queue and preloading: {url}")
    await preload_song(ctx, url)

    # Start playback if no song is currently playing
    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        await play_next_song(ctx)

async def preload_song(ctx, url):
    """Download song in the background and add to queue."""
    loop = asyncio.get_event_loop()
    with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none']  # Select audio-only formats
            if not audio_formats:
                await ctx.send("No suitable audio streams found.")
                return

            url2 = audio_formats[0]['url']  # Get the best audio format URL
            audio_file = ydl.prepare_filename(info)
            song_queue.append((url2, audio_file, info['title']))  # Queue the stream URL, file path, and title
            await ctx.send(f"Preloaded and added to queue: {info['title']}")
        except Exception as e:
            await ctx.send("An error occurred while preloading the song.")
            print(f"Preload error: {e}")

async def play_next_song(ctx):
    """Play the next song from the preloaded queue."""
    if song_queue:
        url2, audio_file, title = song_queue.popleft()  # Get the preloaded stream URL and title
        await ctx.send(f"Now playing: {title} at {volume * 100}% volume")

        # Play the downloaded file or stream URL using FFmpegOpusAudio
        try:
            ffmpeg_options = get_ffmpeg_options(volume)  # Apply current volume level
            source = discord.FFmpegOpusAudio(url2, **ffmpeg_options)
            ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
                handle_after_play(ctx, audio_file), bot.loop))
        except Exception as e:
            await ctx.send("An error occurred during playback.")
            print(f"Playback error: {e}")

async def handle_after_play(ctx, audio_file):
    """Handles cleanup and playing the next song after the current one finishes."""
    if os.path.exists(audio_file):
        os.remove(audio_file)  # Cleanup the downloaded file
    await play_next_song(ctx)

@bot.command(name="skip", help="Skips the current song")
async def skip(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()  # Stops current song, triggers next song in queue
        await ctx.send("Skipped the song.")
    else:
        await ctx.send("No song is currently playing.")

@bot.command(name="stop", help="Stops playback and clears the queue")
async def stop(ctx):
    song_queue.clear()  # Clear the queue
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()  # Stop the current song
    await ctx.send("Stopped playback and cleared the queue.")
    await cleanup_downloads()

@bot.command(name="pause", help="Pauses the currently playing song")
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused the music.")
    else:
        await ctx.send("No audio is playing currently.")

@bot.command(name="resume", help="Resumes the paused song")
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed the music.")
    else:
        await ctx.send("The music is not paused.")

async def cleanup_downloads():
    """Cleanup any remaining downloaded audio files."""
    for _, audio_file, _ in list(song_queue):
        if os.path.exists(audio_file):
            os.remove(audio_file)
    song_queue.clear()

# Run the bot with your token
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
bot.run(DISCORD_BOT_TOKEN)