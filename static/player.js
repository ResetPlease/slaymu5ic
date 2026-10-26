import { LiveEffects } from "./effects.js";
import { SoundTouchNode } from "./vendor/soundtouch.js";

export class StudioPlayer extends EventTarget {
  constructor() {
    super();
    this.context = null;
    this.buffer = null;
    this.source = null;
    this.processor = null;
    this.position = 0;
    this.startedAt = 0;
    this.speed = 1;
    this.pitch = 0;
    this.volume = 1;
    this.parameters = {};
    this.ending = null;
    this.start = 0;
    this.end = 0;
    this.generation = 0;
    this.frame = 0;
  }

  emit(name) {
    this.dispatchEvent(new Event(name));
  }
  get paused() {
    return !this.source;
  }
  get duration() {
    return this.buffer?.duration || 0;
  }
  get currentTime() {
    return this.source
      ? Math.min(
          this.end,
          this.position +
            (this.context.currentTime - this.startedAt) * this.speed,
        )
      : this.position;
  }
  set currentTime(value) {
    const playing = !this.paused;
    this.pause();
    this.position = Math.max(this.start, Math.min(this.end, value));
    this.emit("timeupdate");
    if (playing) this.play().catch(() => this.emit("error"));
  }

  async initialize() {
    if (!this.context) {
      this.context = new AudioContext();
      this.gain = this.context.createGain();
      this.gain.connect(this.context.destination);
      this.ready = SoundTouchNode.register(
        this.context,
        new URL("./vendor/soundtouch-processor.js", import.meta.url).href,
      );
    }
    await this.ready;
  }

  async decode(data) {
    await this.initialize();
    return this.context.decodeAudioData(data);
  }

  setBuffer(buffer) {
    this.pause();
    this.buffer = buffer;
    this.start = 0;
    this.end = buffer.duration;
    this.position = 0;
    this.emit("loadedmetadata");
    this.emit("timeupdate");
  }

  setRange(start, end) {
    if (
      !this.buffer ||
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      start >= end
    )
      return;
    start = Math.max(0, start);
    end = Math.min(this.duration, end);
    if (start >= end || (this.start === start && this.end === end)) return;
    const playing = !this.paused;
    this.pause();
    this.start = start;
    this.end = end;
    this.position = start;
    this.emit("timeupdate");
    if (playing) this.play().catch(() => this.emit("error"));
  }

  setParameters(parameters) {
    const { speed = 1, pitch = 0, volume = 1 } = parameters;
    this.parameters = parameters;
    this.effects?.setParameters(parameters);
    if (this.source) {
      this.position = this.currentTime;
      this.startedAt = this.context.currentTime;
      this.source.playbackRate.setValueAtTime(speed, this.context.currentTime);
      this.processor.playbackRate.setValueAtTime(
        speed,
        this.context.currentTime,
      );
      this.processor.pitchSemitones.setValueAtTime(
        pitch,
        this.context.currentTime,
      );
    }
    this.speed = speed;
    this.pitch = pitch;
    this.volume = volume;
    if (this.gain)
      this.gain.gain.setTargetAtTime(volume, this.context.currentTime, 0.008);
  }

  async play() {
    if (!this.buffer || this.source) return;
    const generation = ++this.generation;
    await this.initialize();
    await this.context.resume();
    if (generation !== this.generation) return;
    if (this.position < this.start || this.position >= this.end - 0.001)
      this.position = this.start;
    const source = this.context.createBufferSource();
    const processor = new SoundTouchNode({ context: this.context });
    source.buffer = this.buffer;
    source.playbackRate.value = this.speed;
    processor.playbackRate.value = this.speed;
    processor.pitchSemitones.value = this.pitch;
    source.connect(processor);
    this.effects = new LiveEffects(this.context);
    this.effects.setParameters(this.parameters);
    processor.connect(this.effects.input);
    this.effects.output.connect(this.gain);
    this.gain.gain.setValueAtTime(this.volume, this.context.currentTime);
    this.source = source;
    this.processor = processor;
    this.startedAt = this.context.currentTime;
    source.onended = () => {
      if (this.source !== source) return;
      this.ending = setTimeout(
        () => {
          this.position = this.end;
          this.stopNodes();
          this.emit("timeupdate");
          this.emit("pause");
          this.emit("ended");
        },
        (this.effects.tail + 0.08) * 1000,
      );
    };
    source.start(this.startedAt, this.position, this.end - this.position);
    this.emit("play");
    this.tick();
  }

  stopNodes() {
    cancelAnimationFrame(this.frame);
    clearTimeout(this.ending);
    if (!this.source) return;
    const source = this.source;
    this.source = null;
    source.onended = null;
    source.stop();
    source.disconnect();
    this.processor.disconnect();
    this.processor.port.close();
    this.processor = null;
    this.effects.disconnect();
    this.effects = null;
  }

  pause() {
    this.generation++;
    this.position = this.currentTime;
    this.stopNodes();
    this.emit("pause");
  }

  tick() {
    this.emit("timeupdate");
    if (!this.paused) this.frame = requestAnimationFrame(() => this.tick());
  }
}
